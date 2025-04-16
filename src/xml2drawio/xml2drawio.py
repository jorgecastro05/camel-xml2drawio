import configargparse
from lxml import etree, objectify
from rich import console
from rich.console import Console
import importlib.metadata
import re
import sys
import uuid

__version__ = importlib.metadata.version('camel-xml2drawio')
ns = {
    "camel": "http://camel.apache.org/schema/spring",
    "beans": "http://www.springframework.org/schema/beans"
}

console = Console()


class Converter:

    X_POS = 300
    Y_POS = 0

    GROOVY_TEMPLATE = '''
        String groovy_>>> index <<< = >>> transformed <<< 
'''

    BEAN_TEMPLATE = '''
    @Autowired
    >>> bean type <<< >>> bean name <<<;
'''

    DIAGRAM_TEMPLATE = '''
<mxGraphModel dx="1120" dy="489" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="850" pageHeight="1100" math="0" shadow="0">
  <root>
    <mxCell id="0" />
    <mxCell id="1" parent="0" />
        >>> routes <<<
  </root>
</mxGraphModel>
    '''

    def __init__(self):
        self.dsl_route = ''
        self.endpoints = {}
        self.bean_refs = {}
        self.indentation = 2
        self.groovy_transformations = {}

    def xml_to_drawio(self):
        p = configargparse.ArgParser(
            description="Transforms xml routes to dsl routes " + __version__)
        p.add_argument('--xml', metavar='xml', type=str,
                       help='xml camel context file', required=True, env_var='XML_CTX_INPUT')
        p.add_argument('--beans', metavar='beans', type=str,
                       help='use beans instead processors', required=False, env_var='USE_BEANS')
        args = p.parse_args()
        with open(args.xml, "r") as xml_file:
            parser = etree.XMLParser(remove_comments=True)
            data = objectify.parse(xml_file, parser=parser)
            console.log(" XML 2 Draw IO Utility ", style="bold red")
            root = data.getroot()

            # Beans
            bean_definitions = []
            for bean in root.findall('.//beans:bean', ns):
                name = bean.attrib['id']
                bean_type = bean.attrib['class']
                if 'PropertyPlaceholderConfigurer' in bean_type:
                    continue

                self.bean_refs[name] = bean_type

                bean = Converter.BEAN_TEMPLATE \
                    .replace('>>> bean type <<<', bean_type) \
                    .replace('>>> bean name <<<', name)

                bean_definitions.append(bean)

            # Multiline groovy transforms
            for idx, node in enumerate(root.findall('.//camel:groovy', ns)):
                code_hash, text = self.preformat_groovy_transformation(node)
                transformed = Converter.GROOVY_TEMPLATE \
                    .replace('>>> index <<<', str(idx)) \
                    .replace('>>> transformed <<<', ' + \n'.join(self.process_multiline_groovy(text)) + ';')

                self.groovy_transformations[code_hash] = {
                    'index': idx,
                    'transformation': transformed
                }

            # Camel Contexts
            for idx, camelContext in enumerate(root.findall('camel:camelContext', ns)):
                if 'id' in camelContext.attrib:
                    console.log("processing camel context", camelContext.attrib['id'])

                class_name = camelContext.attrib['id'] if 'id' in camelContext.attrib else f'camelContext{str(idx)}'
                class_name = class_name.capitalize()

                self.get_namespaces(camelContext)
                self.dsl_route += self.analyze_node(camelContext)

            groovy_transformations = '\n\n'.join([v['transformation'] for k, v in self.groovy_transformations.items()])

            dsl_route = Converter.DIAGRAM_TEMPLATE \
                .replace(">>> groovy transformations <<<", groovy_transformations) \
                .replace(">>> beans <<<", ''.join(bean_definitions)) \
                .replace(">>> class name <<<", class_name) \
                .replace(">>> routes <<<", self.dsl_route)

            print("draw io diagram:\n", dsl_route)

    @staticmethod
    def get_namespaces(node):
        console.log("namespaces:", node.nsmap)

    def analyze_node(self, node):
        dslText = ""
        for child in node:
            node_name = child.tag.partition('}')[2]

            # Skip property placeholders
            if node_name == 'propertyPlaceholder':
                continue

            process_function_name = node_name + "_def"
            console.log("processing node", node_name, child.tag, child.sourceline)
            self.X_POS += 50
            next_node = getattr(self, process_function_name, None)
            if next_node is None:
                console.log("unknown node", process_function_name, child.sourceline)
                sys.exit(1)
            dslText += getattr(self, process_function_name)(child)
        return dslText

    def analyze_element(self, node):
        node_name = node.tag.partition('}')[2] + "_def"
        console.log("processing node", node_name, node.tag, node.sourceline)
        self.X_POS += 50
        return getattr(self, node_name)(node)

    def route_def(self, node):
        route_def = self.analyze_node(node)
        # route_def += self.indent('.end();\n')
        self.indentation -= 1
        return route_def

    def dataFormats_def(self, node):
        dataformats = self.analyze_node(node)
        return dataformats

    def json_def(self, node):
        # name = node.attrib['id']
        # library = f'JsonLibrary.{node.attrib["library"]}' if 'library' in node.attrib else ''

        # json_dataformat = ''

        # if 'jsonView' in node.attrib and node.attrib['jsonView'] == 'true':
        #     json_dataformat = self.indent('// TODO: Review jsonView for this data format')

        # json_dataformat += self.indent(f'JsonDataFormat {name} = new JsonDataFormat({library});')

        # if 'unmarshalTypeName' in node.attrib:
        #     json_dataformat += self.indent(f'{name}.unmarshalType({node.attrib["unmarshalTypeName"]}.class);')

        # return json_dataformat + '\n'
        return ''

    def endpoint_def(self, node):
        endpoint_id = node.attrib['id']
        uri = node.attrib['uri']
        self.endpoints[endpoint_id] = uri
        return ""

    def multicast_def(self, node):
        xml_def = f''''<mxCell id="{uuid.uuid4()}" value="" style="html=1;strokeWidth=2;outlineConnect=0;dashed=0;align=center;fontSize=8;fillColor=#c0f5a9;verticalLabelPosition=bottom;verticalAlign=top;shape=mxgraph.eip.recipient_list;" vertex="1" parent="1">
                        <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="150" height="90" as="geometry" />
                     </mxCell>'''
        multicast_def = self.indent(xml_def)
        self.indentation += 1
        multicast_def += self.analyze_node(node)
        self.indentation -= 1
        # multicast_def += self.indent('.end() // end multicast')
        return multicast_def

    def bean_def(self, node):
        ref = node.attrib['ref']
        method = node.attrib['method']
        return self.indent(f'.bean({self.bean_refs[ref]}.class, "{method}")')

    def recipientList_def(self, node):
        xml_def = f''''<mxCell id="{uuid.uuid4()}" value="" style="html=1;strokeWidth=2;outlineConnect=0;dashed=0;align=center;fontSize=8;fillColor=#c0f5a9;verticalLabelPosition=bottom;verticalAlign=top;shape=mxgraph.eip.recipient_list;" vertex="1" parent="1">
                        <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="150" height="90" as="geometry" />
                     </mxCell>'''
        recipient_def = self.indent(xml_def)
        recipient_def += self.analyze_node(node)
        # recipient_def += self.indent('.end() // end recipientList')
        return recipient_def

    def errorHandler_def(self, node):
        if node.attrib['type'] == "DefaultErrorHandler":
            return self.indent('defaultErrorHandler().setRedeliveryPolicy(policy);')
        else:
            return ""

    def redeliveryPolicyProfile_def(self, node):
        policy_def = "\nRedeliveryPolicy policy = new RedeliveryPolicy()"
        if "maximumRedeliveries" in node.attrib:
            policy_def += ".maximumRedeliveries(" + node.attrib["maximumRedeliveries"] + ")"
        if "retryAttemptedLogLevel" in node.attrib:
            policy_def += ".retryAttemptedLogLevel(LoggingLevel." + node.attrib["retryAttemptedLogLevel"] + ")"
        if "redeliveryDelay" in node.attrib:
            policy_def += ".redeliveryDelay(" + node.attrib["redeliveryDelay"] + ")"
        if "logRetryAttempted" in node.attrib:
            policy_def += ".logRetryAttempted(" + node.attrib["logRetryAttempted"] + ")"
        if "logRetryStackTrace" in node.attrib:
            policy_def += ".logRetryStackTrace(" + node.attrib["logRetryStackTrace"] + ")"
        policy_def += ";"
        return policy_def

    def onException_def(self, node):
        # exceptions = []
        # for exception in node.findall("camel:exception", ns):
        #     exceptions.append(exception.text + ".class")
        #     node.remove(exception)
        # exceptions = ','.join(exceptions)
        # onException_def = self.indent('onException(' + exceptions + ')')

        # indented = False

        # handled = node.find("camel:handled", ns)
        # if handled is not None:
        #     if not indented:
        #         self.indentation += 1
        #         indented = True

        #     onException_def += self.indent('.handled(' + handled[0].text + ')')

        #     node.remove(handled)

        # redeliveryPolicy = node.find('camel:redeliveryPolicy', ns)
        # if redeliveryPolicy is not None:
        #     if not indented:
        #         self.indentation += 1
        #         indented = True

        #     onException_def += self.indent('.maximumRedeliveries(' + redeliveryPolicy.attrib['maximumRedeliveries'] +
        #                                    ')' if 'maximumRedeliveries' in redeliveryPolicy.attrib else '')
        #     onException_def += self.indent('.redeliveryDelay(' + redeliveryPolicy.attrib['redeliveryDelay'] +
        #                                    ')' if 'redeliveryDelay' in redeliveryPolicy.attrib else '')
        #     onException_def += self.indent('.retryAttemptedLogLevel(LoggingLevel.' +
        #                                    redeliveryPolicy.attrib['retryAttemptedLogLevel'] + \
        #                                    ')' if 'retryAttemptedLogLevel' in redeliveryPolicy.attrib else '')
        #     onException_def += self.indent('.retriesExhaustedLogLevel(LoggingLevel.' +
        #                                    redeliveryPolicy.attrib['retriesExhaustedLogLevel'] +
        #                                    ')' if 'retriesExhaustedLogLevel' in redeliveryPolicy.attrib else '')
        #     node.remove(redeliveryPolicy)

        # if 'redeliveryPolicyRef' in node.attrib:
        #     onException_def += self.indent('.redeliveryPolicy(policy)')

        # onException_def += self.analyze_node(node)
        # onException_def += self.indent('.end();\n')

        # if indented:
        #     self.indentation -= 1

        #return onException_def
        return ''

    def description_def(self, node):
        #return self.indent(f'.description("{node.text}")')
        return ''

    def from_def(self, node):
        routeFrom = self.deprecatedProcessor(node.attrib['uri'])
        routeId = node.getparent().attrib['id'] if 'id' in node.getparent().keys() else routeFrom

        xml_def = f'''<mxCell id="{routeId}" value="{routeFrom}" style="fillColor=#c0f5a9;dashed=0;outlineConnect=0;strokeWidth=2;html=1;align=center;fontSize=12;verticalLabelPosition=bottom;verticalAlign=top;shape=mxgraph.eip.polling_consumer;" vertex="1" parent="1">
                <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="150" height="90" as="geometry" /></mxCell>'''

        from_def = self.indent(xml_def)
        from_def += self.analyze_node(node)
        return from_def

    def log_def(self, node):
        # message = self.deprecatedProcessor(node.attrib['message'])
        # if 'loggingLevel' in node.attrib and node.attrib['loggingLevel'] != 'INFO':
        #     return self.indent(f'.log(LoggingLevel.{node.attrib["loggingLevel"]}, "{message}"){self.handle_id(node)}')
        # else:
        #     return self.indent(f'.log("{message}"){self.handle_id(node)}')
        return ''

    def choice_def(self, node):
        xml_def = f'''<mxCell id="{uuid.uuid4()}" value="" style="html=1;strokeWidth=2;outlineConnect=0;dashed=0;align=center;fontSize=8;fillColor=#c0f5a9;verticalLabelPosition=bottom;verticalAlign=top;shape=mxgraph.eip.content_based_router;" vertex="1" parent="1">
                    <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="150" height="90" as="geometry" /></mxCell>'''
        choice_def = self.indent(xml_def)
        self.indentation += 1
        choice_def += self.analyze_node(node)
        self.indentation -= 1

        # choice_def += self.indent(f'.end() // end choice (source line: {str(node.sourceline)})')

        return choice_def

    def when_def(self, node):
        # when_def = self.indent('.when(' + self.analyze_element(node[0]) + ')' + self.handle_id(node))
        # node.remove(node[0])
        # self.indentation += 1
        when_def = ''
        when_def += self.analyze_node(node)
        # self.indentation -= 1
        # when_def += self.indent(f'.endChoice() // (source line: {str(node.sourceline)})')
        return when_def

    def otherwise_def(self, node):
        # otherwise_def = self.indent(f'.otherwise(){self.handle_id(node)}')
        # self.indentation += 1
        otherwise_def = ''
        otherwise_def += self.analyze_node(node)
        # self.indentation -= 1
        # otherwise_def += self.indent(f'.endChoice() // (source line: {str(node.sourceline)})')
        return otherwise_def

    def simple_def(self, node):
        # result_type = f', {node.attrib["resultType"]}.class' if 'resultType' in node.attrib else ''
        # expression = self.deprecatedProcessor(node.text) if node.text is not None else ''
        # return f'simple("{expression.strip()}"{result_type}){self.handle_id(node)}'
        return ''

    def constant_def(self, node):
        # expression = node.text if node.text is not None else ''
        # return f'constant("{expression}"){self.handle_id(node)}'
        return ''

    def groovy_def(self, node):
        # code_hash, text = self.preformat_groovy_transformation(node)
        # groovy_transformation = self.groovy_transformations[code_hash]
        # return f'groovy(groovy_{str(groovy_transformation["index"])}){self.handle_id(node)}'
        return ''

    def xpath_def(self, node):
        # result_type = f', {node.attrib["resultType"]}.class' if 'resultType' in node.attrib else ''
        # expression = node.text if node.text is not None else ''
        # return f'xpath("{expression}"{result_type}){self.handle_id(node)}'
        return ''

    def jsonpath_def(self, node):
        # result_type = f', {node.attrib["resultType"]}.class' if 'resultType' in node.attrib else ''
        # expression = node.text if node.text is not None else ''
        # return f'jsonpath("{expression}"{result_type}){self.handle_id(node)}'
        return ''

    def to_definition(self, node, to_type):
        uri = self.componentOptions(node.attrib['uri'])
        if 'ref:' in uri:
            uri = self.endpoints[uri[4:]]

        uri = self.deprecatedProcessor(uri)

        #pattern = node.attrib['pattern'] if 'pattern' in node.attrib else ''
        #exchangePattern = f'ExchangePattern.{pattern}, ' if pattern and pattern in ['InOnly', 'InOut'] else ''

        #node_id = self.handle_id(node)

        return self.indent(f'{to_type}')

    def to_def(self, node):
        parent_id = uuid.uuid4()
        xml_def = f'''<mxCell id="{parent_id}" value="TO_DEFINITION" style="strokeWidth=2;dashed=0;align=center;fontSize=12;shape=rect;verticalLabelPosition=bottom;verticalAlign=top;fillColor=#c0f5a9;html=1;" vertex="1" parent="1">
        <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="150" height="90" as="geometry" />
        </mxCell>
        <mxCell id="{uuid.uuid4()}" value="" style="html=1;strokeWidth=1;dashed=0;align=center;fontSize=8;shape=rect;" vertex="1" parent="{parent_id}">
            <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="40" height="40" as="geometry" />
        </mxCell>'''
        return self.to_definition(node, xml_def)

    def toD_def(self, node):
        xml_def = f'''<mxCell id="{uuid.uuid4()}" value="TOD_DEFINITION" style="html=1;strokeWidth=2;outlineConnect=0;dashed=0;align=center;fontSize=12;fillColor=#c0f5a9;verticalLabelPosition=bottom;verticalAlign=top;shape=mxgraph.eip.dynamic_router;" vertex="1" parent="1">
                        <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="150" height="90" as="geometry" />
                    </mxCell>'''
        return self.to_definition(node, xml_def)

    def setBody_def(self, node):
        predicate = self.analyze_element(node[0])
        groovy_predicate = f'.{predicate}' if predicate.startswith('groovy') else ''
        predicate = '' if groovy_predicate else predicate
        xml_def = f'''<mxCell id="{uuid.uuid4()}" value="{predicate}" style="html=1;strokeWidth=2;outlineConnect=0;dashed=0;align=center;fontSize=8;shape=mxgraph.eip.message_translator;fillColor=#c0f5a9;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="1">
                        <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="150" height="90" as="geometry" />
                    </mxCell>'''
        return self.indent(xml_def)

    def convertBodyTo_def(self, node):
        # return self.setBody_def(self, node)
        return ''

    def unmarshal_def(self, node):
        # return self.setBody_def(self, node)
        return ''

    def marshal_def(self, node):
        # return self.setBody_def(self, node)
        return ''

    def jaxb_def(self, node):
        # if 'prettyPrint' in node.attrib:
        #     return '.jaxb("' + node.attrib['contextPath'] + '")'
        # else:
        #     return '.jaxb("' + node.attrib['contextPath'] + '")'
        return ''

    def base64_def(self, node):
        # return '.base64()'
        return ''

    def setHeader_def(self, node):
        # name_attrib = 'headerName' if 'headerName' in node.attrib else 'name'
        # return self.set_expression(node, 'setHeader', node.attrib[name_attrib])
        return ''

    def setProperty_def(self, node):
        # name_attrib = 'propertyName' if 'propertyName' in node.attrib else 'name'
        # return self.set_expression(node, 'setProperty', node.attrib[name_attrib])
        return ''

    def setExchangePattern_def(self, node):
        #return self.set_expression(node, 'setExchangePattern', f'ExchangePattern.{node.attrib["pattern"]}')
        return ''

    def process_def(self, node):
        #return self.indent(f'.process({node.attrib["ref"]}){self.handle_id(node)}')
        return ''

    def inOnly_def(self, node):
        # return self.indent(f'.inOnly("{node.attrib["uri"]}")')
        # return to_def(self, node)
        return ''

    def split_def(self, node):
        expression = self.analyze_element(node[0])
        node.remove(node[0])  # remove first child as was processed
        xml_def = f'''<mxCell id="{uuid.uuid4()}" value="{expression}" style="html=1;strokeWidth=2;outlineConnect=0;dashed=0;align=center;fontSize=12;fillColor=#c0f5a9;verticalLabelPosition=bottom;verticalAlign=top;shape=mxgraph.eip.splitter;" vertex="1" parent="1">
                <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="150" height="90" as="geometry" />
            </mxCell>'''
        split_def = self.indent(xml_def)
        # if 'streaming' in node.attrib:
        #     split_def += '.streaming()'
        # if 'strategyRef' in node.attrib:
        #     split_def += f'.aggregationStrategy({node.attrib["strategyRef"]})'
        # if 'parallelProcessing' in node.attrib:
        #     split_def += '.parallelProcessing()'
        # self.indentation += 1
        split_def += self.analyze_node(node)
        # self.indentation -= 1
        # split_def += self.indent('.end() // end split')
        return split_def

    def removeHeaders_def(self, node):
        # exclude_pattern = ', "' + node.attrib['excludePattern'] + '"' if 'excludePattern' in node.attrib else ''
        # return self.indent(f'.removeHeaders("{node.attrib["pattern"]}"{exclude_pattern})')
        return ''

    def removeHeader_def(self, node):
        # return self.indent(f'.removeHeaders("{node.attrib["headerName"]}")')
        return ''

    def xquery_def(self, node):
        # return f'xquery("{node.text}") // xquery not finished please review'
        return ''

    def doTry_def(self, node):
        # doTry_def = self.indent(f'.doTry(){self.handle_id(node)}')
        # self.indentation += 1
        # doTry_def += self.analyze_node(node)
        # self.indentation -= 1
        # doTry_def += self.indent(f'.endDoTry() // (source line: {str(node.sourceline)})')
        # return doTry_def
        return ''

    def doCatch_def(self, node):
        # exceptions = []
        # for exception in node.findall("camel:exception", ns):
        #     exceptions.append(exception.text + ".class")
        #     node.remove(exception)
        # exceptions = ', '.join(exceptions)

        # doCatch_def = self.indent(f'.doCatch({exceptions}){self.handle_id(node)}')

        # self.indentation += 1
        # doCatch_def += self.analyze_node(node)
        # self.indentation -= 1
        # return doCatch_def
        return ''

    def onWhen_def(self, node):
        #onWhen_predicate = self.analyze_element(node[0])
        #node.remove(node[0])
        #return f'.onWhen({onWhen_predicate})'
        return ''

    def doFinally_def(self, node):
        #self.indentation += 1
        doFinally_Def = self.analyze_node(node)
        #self.indentation -= 1
        return doFinally_Def

    def handled_def(self, node):
        #return '.handled(' + node[0].text + ')'
        return ''

    def transacted_def(self, node):
        #transacted_ref = ''
        #return self.indent(f'.transacted({transacted_ref}){self.handle_id(node)}')
        return ''

    def wireTap_def(self, node):
        # if 'executorServiceRef' in node.attrib:
        #     return self.indent(f'.wireTap("{node.attrib["uri"]}"){self.handle_id(node)}.executorServiceRef("profile")')
        # else:
        #     return self.indent(f'.wireTap("{node.attrib["uri"]}"){self.handle_id(node)}')
        xml_def = f'''<mxCell id="{uuid.uuid4()}" value="WIRETAP" style="html=1;strokeWidth=2;outlineConnect=0;dashed=0;align=center;fontSize=12;verticalLabelPosition=bottom;verticalAlign=top;shape=mxgraph.eip.wire_tap;fillColor=#c0f5a9" vertex="1" parent="1">
                        <mxGeometry x="{self.X_POS}" y="{self.Y_POS}" width="150" height="90" as="geometry" />
                    </mxCell>'''
        return xml_def

    def language_def(self, node):
        #return 'language("' + node.attrib['language'] + '","' + node.text + '")'
        return ''

    def threads_def(self, node):
        # threads_def = None
        # maxPoolSize = node.attrib['maxPoolSize'] if 'maxPoolSize' in node.attrib else None
        # poolSize = node.attrib['poolSize'] if 'poolSize' in node.attrib else None
        # if poolSize is None and maxPoolSize is not None:
        #     poolSize = maxPoolSize
        # if poolSize is not None and maxPoolSize is None:
        #     maxPoolSize = poolSize
        # if 'threadName' in node.attrib:
        #     threads_def = '\n.threads(' + poolSize + ',' + maxPoolSize + ',"' + node.attrib['threadName'] + '")'
        # else:
        #     threads_def = '\n.threads(' + poolSize + ',' + maxPoolSize + ')'

        threads_def += self.analyze_node(node)
        # threads_def += "\n.end() //end threads"
        return threads_def

    def delay_def(self, node):
        #delay_def = '\n.delay().'
        delay_def += self.analyze_node(node)
        return delay_def

    def javaScript_def(self, node):
        #return 'new JavaScriptExpression("' + node.text + '")'
        return ''

    def threadPoolProfile_def(self, node):
        # profileDef = '\nThreadPoolProfile profile = new ThreadPoolProfile();'
        # if 'defaultProfile' in node.attrib:
        #     profileDef += '\nprofile.setDefaultProfile(' + node.attrib['defaultProfile'] + ');'
        # if 'id' in node.attrib:
        #     profileDef += '\nprofile.setId("' + node.attrib['id'] + '");'
        # if 'keepAliveTime' in node.attrib:
        #     profileDef += '\nprofile.setKeepAliveTime(' + node.attrib['keepAliveTime'] + 'L);'
        # if 'maxPoolSize' in node.attrib:
        #     profileDef += '\nprofile.setMaxPoolSize(' + node.attrib['maxPoolSize'] + ');'
        # if 'maxQueueSize' in node.attrib:
        #     profileDef += '\nprofile.setMaxQueueSize(' + node.attrib['maxQueueSize'] + ');'
        # if 'poolSize' in node.attrib:
        #     profileDef += '\nprofile.setPoolSize(' + node.attrib['poolSize'] + ');'
        # if 'rejectedPolicy' in node.attrib:
        #     if node.attrib['rejectedPolicy'] == 'Abort':
        #         profileDef += '\nprofile.setRejectedPolicy(ThreadPoolRejectedPolicy.Abort);'
        # return profileDef
        return ''

    def throwException_def(self, node):
        # has_ref = 'ref' in node.attrib
        # exception_type = '' if has_ref else node.attrib['exceptionType']
        # message = f'TODO: Please review, throwException has changed with Java DSL (source line: ' \
        #           + str(node.sourceline) \
        #           + ')"' \
        #     if has_ref else node.attrib['message']

        # throwException_def = self.indent(f'.throwException({exception_type}.class, "{message}"){self.handle_id(node)}')
        throwException_def += self.analyze_node(node)
        return throwException_def

    def spel_def(self, node):
        #return 'SpelExpression.spel("' + node.text + '")'
        return ''

    def loop_def(self, node):
        # loop_def = self.indent(f'.loop({self.analyze_element(node[0])}){self.handle_id(node)}')
        # node.remove(node[0])
        # self.indentation += 1
        loop_def += self.analyze_node(node)
        # self.indentation -= 1
        # loop_def += self.indent(f'.end() // end loop (source line: {str(node.sourceline)})')
        return loop_def

    def aggregate_def(self, node):
        # aggregate_def = self.indent('.aggregate()')
        # aggregate_def += self.analyze_element(node[0])
        # if 'completionTimeout' in node.attrib:
        #     aggregate_def += f'.completionTimeout({node.attrib["completionTimeout"]})'

        # if 'strategyRef' in node.attrib:
        #     aggregate_def += f'.aggregationStrategy({node.attrib["strategyRef"]})'

        # node.remove(node[0])  # remove first child as was processed
        # self.indentation += 1
        aggregate_def += self.analyze_node(node)
        # self.indentation -= 1
        # aggregate_def += self.indent('.end() // end aggregate')
        return aggregate_def

    def correlationExpression_def(self, node):
        #return '.' + self.analyze_node(node)
        return ''

    def tokenize_def(self, node):
        #return f'tokenize("{node.attrib["token"]}")'
        return ''

    def stop_def(self, node):
        #return self.indent('.stop()')
        return ''

    def restConfiguration_def(self, node):

        # rest_configuration = self.indent('restConfiguration()')

        # self.indentation += 1

        # if 'contextPath' in node.attrib:
        #     rest_configuration += self.indent(f'.contextPath("{node.attrib["contextPath"]}")')

        # if 'bindingMode' in node.attrib:
        #     rest_configuration += self.indent(f'.bindingMode(RestBindingMode.{node.attrib["bindingMode"]})')

        # if 'component' in node.attrib:
        #     rest_configuration += self.indent(f'.component({node.attrib["component"]})')

        # if 'port' in node.attrib:
        #     rest_configuration += self.indent(f'.port({node.attrib["port"]})')

        # rest_configuration += self.analyze_node(node)
        # self.indentation -= 1

        # rest_configuration += ';\n'

        #return rest_configuration
        return ''

    def componentProperty_def(self, node):
        #return self.indent(f'.componentProperty("{node.attrib["key"]}", "{node.attrib["value"]}")')
        return ''

    def dataFormatProperty_def(self, node):
        #return self.indent(f'.dataFormatProperty("{node.attrib["key"]}", "{node.attrib["value"]}")')
        return ''

    def rest_def(self, node):
        # path = node.attrib['path'] if 'path' in node.attrib else ''
        # rest = self.indent(f'rest("{path}")' if path else 'rest()')
        # self.indentation += 1
        # rest += self.analyze_node(node)
        # self.indentation -= 1

        # rest += ';\n'
        # return rest
        return ''

    def get_def(self, node):
        #return self.generic_rest_def(node, 'get')
        return ''

    def post_def(self, node):
        #return self.generic_rest_def(node, 'post')
        return ''

    def param_def(self, node):
        # param = '.param()'
        # param += '.endParam()'

        # if 'name' in node.attrib:
        #     param += f'.name("{node.attrib["name"]}")'

        # if 'required' in node.attrib:
        #     param += f'.required({node.attrib["required"]})'

        # if 'dataFormat' in node.attrib:
        #     param += f'.dataFormat(RestParamType.{node.attrib["dataFormat"]})'

        # if 'type' in node.attrib:
        #     param += f'.type(RestParamType.{node.attrib["type"]})'

        # if 'description' in node.attrib:
        #     param += f'.description("{node.attrib["description"]}")'

        # if 'dataType' in node.attrib:
        #     param += f'.dataType("{node.attrib["dataType"]}")'

        # return self.indent(param)
        # # param().name("id").type(path).description("The id of the user to get").dataType("int").endParam()
        return ''

    def generic_rest_def(self, node, verb):
        # uri = node.attrib['uri'] if 'uri' in node.attrib else ''
        # rest_call = self.indent(f'.{verb}("{uri}")' if uri else f'{verb}()')
        # self.indentation += 1

        # if 'bindingMode' in node.attrib:
        #     rest_call += self.indent(f'.bindingMode(RestBindingMode.{node.attrib["bindingMode"]})')

        # if 'consumes' in node.attrib:
        #     rest_call += self.indent(f'.consumes("{node.attrib["consumes"]}")')

        # if 'produces' in node.attrib:
        #     rest_call += self.indent(f'.produces("{node.attrib["produces"]}")')

        # if 'type' in node.attrib:
        #     rest_call += self.indent(f'.type({node.attrib["type"]}.class)')

        # if 'outType' in node.attrib:
        #     rest_call += self.indent(f'.outType({node.attrib["outType"]}.class)')

        # rest_call += self.analyze_node(node)

        # self.indentation -= 1

        # return rest_call
        return ''

    # Text deprecated processor for camel deprecated endpoints and features
    @staticmethod
    def deprecatedProcessor(text):
        # exchange property in simple expressions
        text = re.sub('\${property\.(\w+\.?\w+)}', r'${exchangeProperty.\1}', text)
        text = re.sub('\${header\.(\w+\.?\w+)}', r'${headers.\1}', text)
        text = re.sub('"', "'", text)  # replace all occurrences from " to '
        text = re.sub('\n', "", text)  # remove all endlines

        # convert all property references
        for match in re.finditer(r"\$(\{[\w\.\_]+\})", text):
            if 'exchangeProperty' not in match.group(0) and 'headers' not in match.group(0):
                text = text.replace(match.group(0), '{' + match.group(1) + '}')
                text = text.replace(match.group(0), f'{{{match.group(1)}}}')

        return text

    # Text processor for apply custom options in to endpoints
    @staticmethod
    def componentOptions(text):
        if "velocity:" in text:
            text += "?contentCache=true"
        return text

    def set_expression(self, node, set_method, parameter=None):
        predicate = self.analyze_element(node[0])
        groovy_predicate = f'.{predicate}' if predicate.startswith("groovy") else ''
        predicate = '' if groovy_predicate else predicate
        parameter = f'"{parameter.strip()}", ' if parameter else ''
        return self.indent(f'.{set_method}({parameter}{predicate.strip()}){groovy_predicate}')

    def process_multiline_groovy(self, text):
        parts = re.split('\r?\n', text)
        parts = [self.format_multiline_groovy(idx, part) for idx, part in enumerate(parts)]
        return parts

    @staticmethod
    def format_multiline_groovy(idx, part):
        indentation = '' if idx == 0 else ' ' * 16
        return f'{indentation}"{part}"'

    @staticmethod
    def preformat_groovy_transformation(node):
        text = node.text.replace('"', '\'')
        return hash(text), text

    @staticmethod
    def handle_id(node):
        return f'.id("{node.attrib["id"]}")' if 'id' in node.attrib else ''

    def indent(self, text: str) -> str:
        return '\n' + (' ' * 4 * self.indentation) + text if text else ''


if __name__ == "__main__":
    converter = Converter()
    converter.xml_to_drawio()


def main():
    converter = Converter()
    converter.xml_to_drawio()