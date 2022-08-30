# File: parser_helper.py
#
# Copyright (c) 2017-2022 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied. See the License for the specific language governing permissions
# and limitations under the License.
import re
from io import StringIO
from parser import TextIOCParser

import magic
import phantom.app as phantom
from bs4 import BeautifulSoup
from bs4.element import Comment
from pdfminer.six.converter import TextConverter
from pdfminer.six.layout import LAParams
from pdfminer.six.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.six.pdfpage import PDFPage

MAGIC_FORMATS = [
    (re.compile('^PDF '), 'pdf'),
    (re.compile('^HTML '), 'html'),
    (re.compile('(ASCII|Unicode) text'), 'txt')
]


def visible_tags(element):
    if element.parent.name in ['style', 'script', 'meta']:
        return False
    if isinstance(element, Comment):
        return False
    return True


def _html_to_text(html_text):
    try:
        soup = BeautifulSoup(html_text, 'html.parser')
        read_text = soup.findAll(text=True)
        visible_text = filter(visible_tags, read_text)
        text = ' '.join(t.strip() for t in visible_text)
        hrefs = soup.findAll('a', href=True)
        # pylint: disable=invalid-sequence-index
        text += ' '.join(x['href'] for x in hrefs)
    except Exception as e:
        return phantom.APP_ERROR, "Error parsing html: {}".format(str(e)), None
    return phantom.APP_SUCCESS, None, text


def _pdf_to_text(pdf_contents):
    try:
        pagenums = set()
        output = StringIO()
        pdf_contents = StringIO(pdf_contents)
        manager = PDFResourceManager()
        converter = TextConverter(manager, output, laparams=LAParams())
        interpreter = PDFPageInterpreter(manager, converter)
        for page in PDFPage.get_pages(pdf_contents, pagenums):
            interpreter.process_page(page)
        converter.close()
        text = output.getvalue()
        pdf_contents.close()
        output.close()
        return phantom.APP_SUCCESS, None, text
    except Exception as e:
        msg = "Error parsing pdf file: {}".format(str(e))
        return phantom.APP_ERROR, msg, None


def parse_link_contents(base_connector, resp_content):
    """ type: (BaseConnector, str) -> bool, str, dict """
    magic_str = magic.from_buffer(resp_content)
    for regex, file_type in MAGIC_FORMATS:
        if regex.match(magic_str):
            return parse_file(base_connector, resp_content, file_type)
    return phantom.APP_ERROR, "Link is an invalid file type", None


def parse_file(base_connector, file_contents, file_type):
    """ type: (BaseConnector, ActionResult, str) -> bool, list """
    if file_type == 'pdf':
        ret_val, msg, raw_text = _pdf_to_text(file_contents)
    elif file_type == 'html':
        ret_val, msg, raw_text = _html_to_text(file_contents)
    elif file_type == 'txt':
        raw_text = file_contents
    else:
        return phantom.APP_ERROR, "Link is an invalid file type", None

    if phantom.is_fail(ret_val):
        return ret_val, msg, None

    cve = {
        'cef': 'cve',
        'pattern': r'CVE-\d{4}-\d+',
        'name': 'CVE Artifact'
    }
    patterns = TextIOCParser.BASE_PATTERNS
    patterns.append(cve)

    tiocp = TextIOCParser(patterns=patterns)
    try:
        artifacts = tiocp.parse_to_artifacts(raw_text)
    except Exception as e:
        msg = "Error parsing text: {}".format(str(e))
        return phantom.APP_ERROR, msg, None
    return phantom.APP_SUCCESS, None, artifacts
