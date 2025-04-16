import unittest
from xml2drawio.xml2drawio import xml_to_drawio
from unittest import TestCase, mock

class TestScript(unittest.TestCase):

    def test_upper(self):
        self.assertEqual(xml_to_drawio(), 0)

if __name__ == '__main__':
    unittest.main()