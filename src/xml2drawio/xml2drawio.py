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

    DIAGRAM_TEMPLATE = '''
## https://drawio-app.com/blog/import-from-csv-to-drawio/
# label: %component%
# style: shape=%shape%;html=1;strokeWidth=2;outlineConnect=0;dashed=0;align=center;fontSize=12;fillColor=#c0f5a9;verticalLabelPosition=bottom;verticalAlign=top;
# namespace: csvimport-
# connect: {"from":"refs", "to":"id", "invert":false, "style": \\
#            "curved=0;endArrow=none;endFill=0;dashed=0;strokeColor=#6c8ebf;"}
# width: 150
# height: 90
# padding: 1
# ignore: id,shape,fill,stroke,refs
# nodespacing: 5
# levelspacing: 5
# edgespacing: 5
# layout: horizontaltree
## CSV data starts below this line
id,component,shape,refs
>>> routes <<<
    '''

    def __init__(self):
        self.dsl_route = ''
        self.endpoints = {}
        self.bean_refs = {}

    def xml_to_drawio(self):
        p = configargparse.ArgParser(
            description="Transforms xml routes to eip draw io diagram " + __version__)
        p.add_argument('--xml', metavar='xml', type=str, help='xml camel context file', required=True, env_var='XML_CTX_INPUT')
        
        args = p.parse_args()
        with open(args.xml, "r") as xml_file:
            parser = etree.XMLParser(remove_comments=True)
            data = objectify.parse(xml_file, parser=parser)
            console.log(" XML 2 Draw IO Utility ", style="bold red")
            root = data.getroot()

            # Camel Contexts
            for idx, camelContext in enumerate(root.findall('camel:camelContext', ns)):
                if 'id' in camelContext.attrib:
                    console.log("processing camel context", camelContext.attrib['id'])

                class_name = camelContext.attrib['id'] if 'id' in camelContext.attrib else f'camelContext{str(idx)}'
                class_name = class_name.capitalize()
                context_id = uuid.uuid4()
                self.get_namespaces(camelContext)
                self.dsl_route += self.analyze_node(camelContext, context_id)

            dsl_route = Converter.DIAGRAM_TEMPLATE \
                .replace(">>> routes <<<", self.dsl_route)

            print("draw io diagram:\n", dsl_route)

    @staticmethod
    def get_namespaces(node):
        console.log("namespaces:", node.nsmap)

    def analyze_node(self, node, parent_id):
        dsl_text = ""
        for child in node:
            node_name = child.tag.partition('}')[2]

            # Skip property placeholders
            if node_name == 'propertyPlaceholder':
                continue

            process_function_name = node_name + "_def"
            console.log("processing node", node_name, child.tag, child.sourceline)
            next_node = getattr(self, process_function_name, None)
            if next_node is None:
                console.log("unknown node", process_function_name, child.sourceline)
                sys.exit(1)
            dsl_text += getattr(self, process_function_name)(child, parent_id)
        return dsl_text

    def analyze_element(self, node, parent_id):
        node_name = node.tag.partition('}')[2] + "_def"
        console.log("processing node", node_name, node.tag, node.sourceline)
        return getattr(self, node_name)(node, parent_id)

    def route_def(self, node, parent_id):
        route_def = self.analyze_node(node, parent_id)
        return route_def

    def dataFormats_def(self, node, parent_id):
        dataformats = self.analyze_node(node, parent_id)
        return dataformats

    def json_def(self, node, parent_id):
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

    def endpoint_def(self, node, parent_id):
        endpoint_id = node.attrib['id']
        uri = node.attrib['uri']
        self.endpoints[endpoint_id] = uri
        return ""

    def multicast_def(self, node, parent_id):
        node_id= uuid.uuid4()
        csv_def = f'{node_id},multicast,mxgraph.eip.recipient_list,{parent_id}\n'
        multicast_def = csv_def
        
        multicast_def += self.analyze_node(node, node_id)
        
        # multicast_def += self.indent('.end() // end multicast')
        return multicast_def

    def bean_def(self, node, parent_id):
        ref = node.attrib['ref']
        method = node.attrib['method']
        return self.indent(f'.bean({self.bean_refs[ref]}.class, "{method}")')

    def recipientList_def(self, node, parent_id):
        node_id= uuid.uuid4()
        csv_def = f'{node_id},recipient list,mxgraph.eip.recipient_list,{parent_id}\n'
        recipient_def = csv_def
        recipient_def += self.analyze_node(node, node_id)
        # recipient_def += self.indent('.end() // end recipientList')
        return recipient_def

    def errorHandler_def(self, node, parent_id):
        if node.attrib['type'] == "DefaultErrorHandler":
            return self.indent('defaultErrorHandler().setRedeliveryPolicy(policy);')
        else:
            return ""

    def redeliveryPolicyProfile_def(self, node, parent_id):
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

    def onException_def(self, node, parent_id):
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
        #         
        #         indented = True

        #     onException_def += self.indent('.handled(' + handled[0].text + ')')

        #     node.remove(handled)

        # redeliveryPolicy = node.find('camel:redeliveryPolicy', ns)
        # if redeliveryPolicy is not None:
        #     if not indented:
        #         
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

        # onException_def += self.analyze_node(node, parent_id)
        # onException_def += self.indent('.end();\n')

        # if indented:
        #     

        #return onException_def
        return ''

    def description_def(self, node, parent_id):
        #return self.indent(f'.description("{node.text}")')
        return ''

    def from_def(self, node, parent_id):
        routeFrom = self.deprecatedProcessor(node.attrib['uri'])
        routeId = node.getparent().attrib['id'] if 'id' in node.getparent().keys() else routeFrom
        node_id= uuid.uuid4()
        csv_def = f'{parent_id},{routeId},mxgraph.eip.polling_consumer\n'
        from_def = csv_def
        from_def += self.analyze_node(node,node_id)
        return from_def

    def log_def(self, node, parent_id):
        # message = self.deprecatedProcessor(node.attrib['message'])
        # if 'loggingLevel' in node.attrib and node.attrib['loggingLevel'] != 'INFO':
        #     return self.indent(f'.log(LoggingLevel.{node.attrib["loggingLevel"]}, "{message}"){self.handle_id(node)}')
        # else:
        #     return self.indent(f'.log("{message}"){self.handle_id(node)}')
        return ''

    def choice_def(self, node, parent_id):
        node_id = uuid.uuid4()
        csv_def = f'{node_id},choice,mxgraph.eip.content_based_router,{parent_id}\n'
        choice_def = csv_def
        
        choice_def += self.analyze_node(node, node_id)
        

        # choice_def += self.indent(f'.end() // end choice (source line: {str(node.sourceline)})')

        return choice_def

    def when_def(self, node, parent_id):
        # when_def = self.indent('.when(' + self.analyze_element(node[0]) + ')' + self.handle_id(node))
        # node.remove(node[0])
        # 
        when_def = ''
        when_def += self.analyze_node(node, parent_id)
        # 
        # when_def += self.indent(f'.endChoice() // (source line: {str(node.sourceline)})')
        return when_def

    def otherwise_def(self, node, parent_id):
        # otherwise_def = self.indent(f'.otherwise(){self.handle_id(node)}')
        # 
        otherwise_def = ''
        otherwise_def += self.analyze_node(node, parent_id)
        # 
        # otherwise_def += self.indent(f'.endChoice() // (source line: {str(node.sourceline)})')
        return otherwise_def

    def simple_def(self, node, parent_id):
        # result_type = f', {node.attrib["resultType"]}.class' if 'resultType' in node.attrib else ''
        # expression = self.deprecatedProcessor(node.text) if node.text is not None else ''
        # return f'simple("{expression.strip()}"{result_type}){self.handle_id(node)}'
        return ''

    def constant_def(self, node, parent_id):
        # expression = node.text if node.text is not None else ''
        # return f'constant("{expression}"){self.handle_id(node)}'
        return ''

    def groovy_def(self, node, parent_id):
        # code_hash, text = self.preformat_groovy_transformation(node)
        # groovy_transformation = self.groovy_transformations[code_hash]
        # return f'groovy(groovy_{str(groovy_transformation["index"])}){self.handle_id(node)}'
        return ''

    def xpath_def(self, node, parent_id):
        # result_type = f', {node.attrib["resultType"]}.class' if 'resultType' in node.attrib else ''
        # expression = node.text if node.text is not None else ''
        # return f'xpath("{expression}"{result_type}){self.handle_id(node)}'
        return ''

    def jsonpath_def(self, node, parent_id):
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

        return to_type

    def to_def(self, node, parent_id):
        node_id = uuid.uuid4()
        csv_def = f'{node_id},to,rect,{parent_id}\n'

        return self.to_definition(node, csv_def)

    def toD_def(self, node, parent_id):
        node_id = uuid.uuid4()
        csv_def = f'{node_id},toD,mxgraph.eip.dynamic_router,{parent_id}\n'
        return self.to_definition(node, node_id)

    def setBody_def(self, node, parent_id):
        predicate = self.analyze_element(node[0], parent_id)
        groovy_predicate = f'.{predicate}' if predicate.startswith('groovy') else ''
        predicate = '' if groovy_predicate else predicate
        node_id = uuid.uuid4()
        csv_def = f'{node_id},{predicate},mxgraph.eip.message_translator,{parent_id}\n'
        return csv_def

    def convertBodyTo_def(self, node, parent_id):
        # return self.setBody_def(self, node)
        return ''

    def unmarshal_def(self, node, parent_id):
        # return self.setBody_def(self, node)
        return ''

    def marshal_def(self, node, parent_id):
        # return self.setBody_def(self, node)
        return ''

    def jaxb_def(self, node, parent_id):
        # if 'prettyPrint' in node.attrib:
        #     return '.jaxb("' + node.attrib['contextPath'] + '")'
        # else:
        #     return '.jaxb("' + node.attrib['contextPath'] + '")'
        return ''

    def base64_def(self, node):
        # return '.base64()'
        return ''

    def setHeader_def(self, node, parent_id):
        # name_attrib = 'headerName' if 'headerName' in node.attrib else 'name'
        # return self.set_expression(node, 'setHeader', node.attrib[name_attrib])
        return ''

    def setProperty_def(self, node, parent_id):
        # name_attrib = 'propertyName' if 'propertyName' in node.attrib else 'name'
        # return self.set_expression(node, 'setProperty', node.attrib[name_attrib])
        return ''

    def setExchangePattern_def(self, node, parent_id):
        #return self.set_expression(node, 'setExchangePattern', f'ExchangePattern.{node.attrib["pattern"]}')
        return ''

    def process_def(self, node, parent_id):
        #return self.indent(f'.process({node.attrib["ref"]}){self.handle_id(node)}')
        return ''

    def inOnly_def(self, node, parent_id):
        # return self.indent(f'.inOnly("{node.attrib["uri"]}")')
        # return to_def(self, node)
        return ''

    def split_def(self, node, parent_id):
        expression = self.analyze_element(node[0])
        node.remove(node[0])  # remove first child as was processed
        node_id = uuid.uuid4()
        csv_def = f'{node_id},{predicate},mxgraph.eip.splitter,{parent_id}\n'
        split_def = csv_def
        # if 'streaming' in node.attrib:
        #     split_def += '.streaming()'
        # if 'strategyRef' in node.attrib:
        #     split_def += f'.aggregationStrategy({node.attrib["strategyRef"]})'
        # if 'parallelProcessing' in node.attrib:
        #     split_def += '.parallelProcessing()'
        # 
        split_def += self.analyze_node(node, node_id)
        # 
        # split_def += self.indent('.end() // end split')
        return split_def

    def removeHeaders_def(self, node, parent_id):
        # exclude_pattern = ', "' + node.attrib['excludePattern'] + '"' if 'excludePattern' in node.attrib else ''
        # return self.indent(f'.removeHeaders("{node.attrib["pattern"]}"{exclude_pattern})')
        return ''

    def removeHeader_def(self, node, parent_id):
        # return self.indent(f'.removeHeaders("{node.attrib["headerName"]}")')
        return ''

    def xquery_def(self, node, parent_id):
        # return f'xquery("{node.text}") // xquery not finished please review'
        return ''

    def doTry_def(self, node, parent_id):
        # doTry_def = self.indent(f'.doTry(){self.handle_id(node)}')
        # 
        # doTry_def += self.analyze_node(node, parent_id)
        # 
        # doTry_def += self.indent(f'.endDoTry() // (source line: {str(node.sourceline)})')
        # return doTry_def
        return ''

    def doCatch_def(self, node, parent_id):
        # exceptions = []
        # for exception in node.findall("camel:exception", ns):
        #     exceptions.append(exception.text + ".class")
        #     node.remove(exception)
        # exceptions = ', '.join(exceptions)

        # doCatch_def = self.indent(f'.doCatch({exceptions}){self.handle_id(node)}')

        # 
        # doCatch_def += self.analyze_node(node, parent_id)
        # 
        # return doCatch_def
        return ''

    def onWhen_def(self, node, parent_id):
        #onWhen_predicate = self.analyze_element(node[0])
        #node.remove(node[0])
        #return f'.onWhen({onWhen_predicate})'
        return ''

    def doFinally_def(self, node, parent_id):
        #
        doFinally_Def = self.analyze_node(node, parent_id)
        #
        return doFinally_Def

    def handled_def(self, node, parent_id):
        #return '.handled(' + node[0].text + ')'
        return ''

    def transacted_def(self, node, parent_id):
        #transacted_ref = ''
        #return self.indent(f'.transacted({transacted_ref}){self.handle_id(node)}')
        return ''

    def wireTap_def(self, node, parent_id):
        # if 'executorServiceRef' in node.attrib:
        #     return self.indent(f'.wireTap("{node.attrib["uri"]}"){self.handle_id(node)}.executorServiceRef("profile")')
        # else:
        #     return self.indent(f'.wireTap("{node.attrib["uri"]}"){self.handle_id(node)}')
        node_id= uuid.uuid4()
        csv_def = f'{node_id},{predicate},mxgraph.eip.wire_tap,{parent_id}\n'
        return csv_def

    def language_def(self, node, parent_id):
        #return 'language("' + node.attrib['language'] + '","' + node.text + '")'
        return ''

    def threads_def(self, node, parent_id):
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

        threads_def += self.analyze_node(node, parent_id)
        # threads_def += "\n.end() //end threads"
        return threads_def

    def delay_def(self, node, parent_id):
        #delay_def = '\n.delay().'
        delay_def += self.analyze_node(node, parent_id)
        return delay_def

    def javaScript_def(self, node, parent_id):
        #return 'new JavaScriptExpression("' + node.text + '")'
        return ''

    def threadPoolProfile_def(self, node, parent_id):
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

    def throwException_def(self, node, parent_id):
        # has_ref = 'ref' in node.attrib
        # exception_type = '' if has_ref else node.attrib['exceptionType']
        # message = f'TODO: Please review, throwException has changed with Java DSL (source line: ' \
        #           + str(node.sourceline) \
        #           + ')"' \
        #     if has_ref else node.attrib['message']

        # throwException_def = self.indent(f'.throwException({exception_type}.class, "{message}"){self.handle_id(node)}')
        throwException_def += self.analyze_node(node, parent_id)
        return throwException_def

    def spel_def(self, node, parent_id):
        #return 'SpelExpression.spel("' + node.text + '")'
        return ''

    def loop_def(self, node, parent_id):
        # loop_def = self.indent(f'.loop({self.analyze_element(node[0])}){self.handle_id(node)}')
        # node.remove(node[0])
        # 
        loop_def += self.analyze_node(node, parent_id)
        # 
        # loop_def += self.indent(f'.end() // end loop (source line: {str(node.sourceline)})')
        return loop_def

    def aggregate_def(self, node, parent_id):
        # aggregate_def = self.indent('.aggregate()')
        # aggregate_def += self.analyze_element(node[0])
        # if 'completionTimeout' in node.attrib:
        #     aggregate_def += f'.completionTimeout({node.attrib["completionTimeout"]})'

        # if 'strategyRef' in node.attrib:
        #     aggregate_def += f'.aggregationStrategy({node.attrib["strategyRef"]})'

        # node.remove(node[0])  # remove first child as was processed
        # 
        aggregate_def += self.analyze_node(node, parent_id)
        # 
        # aggregate_def += self.indent('.end() // end aggregate')
        return aggregate_def

    def correlationExpression_def(self, node, parent_id):
        #return '.' + self.analyze_node(node, parent_id)
        return ''

    def tokenize_def(self, node, parent_id):
        #return f'tokenize("{node.attrib["token"]}")'
        return ''

    def stop_def(self, node, parent_id):
        #return self.indent('.stop()')
        return ''

    def restConfiguration_def(self, node, parent_id):

        # rest_configuration = self.indent('restConfiguration()')

        # 

        # if 'contextPath' in node.attrib:
        #     rest_configuration += self.indent(f'.contextPath("{node.attrib["contextPath"]}")')

        # if 'bindingMode' in node.attrib:
        #     rest_configuration += self.indent(f'.bindingMode(RestBindingMode.{node.attrib["bindingMode"]})')

        # if 'component' in node.attrib:
        #     rest_configuration += self.indent(f'.component({node.attrib["component"]})')

        # if 'port' in node.attrib:
        #     rest_configuration += self.indent(f'.port({node.attrib["port"]})')

        # rest_configuration += self.analyze_node(node, parent_id)
        # 

        # rest_configuration += ';\n'

        #return rest_configuration
        return ''

    def componentProperty_def(self, node, parent_id):
        #return self.indent(f'.componentProperty("{node.attrib["key"]}", "{node.attrib["value"]}")')
        return ''

    def dataFormatProperty_def(self, node, parent_id):
        #return self.indent(f'.dataFormatProperty("{node.attrib["key"]}", "{node.attrib["value"]}")')
        return ''

    def rest_def(self, node, parent_id):
        # path = node.attrib['path'] if 'path' in node.attrib else ''
        # rest = self.indent(f'rest("{path}")' if path else 'rest()')
        # 
        # rest += self.analyze_node(node, parent_id)
        # 

        # rest += ';\n'
        # return rest
        return ''

    def get_def(self, node, parent_id):
        #return self.generic_rest_def(node, 'get')
        return ''

    def post_def(self, node, parent_id):
        #return self.generic_rest_def(node, 'post')
        return ''

    def param_def(self, node, parent_id):
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
        # 

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

        # rest_call += self.analyze_node(node, parent_id)

        # 

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