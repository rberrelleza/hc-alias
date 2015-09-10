import unittest
from app import create_webhook_pattern
import re


class TestApp(unittest.TestCase):

    def test_alias_at_beginning_match(self):
        self.assertRegex("@ops", re.compile(create_webhook_pattern("@ops")))

    def test_alias_anywhere_in_message_match(self):
        self.assertRegex("Who in @ops can help me with permissions?", re.compile(create_webhook_pattern("@ops")))

    def test_alias_with_punctuation_following(self):
        self.assertRegex("Hey @dos, can you help me?", re.compile(create_webhook_pattern("@dos")))

    def test_alias_command_doesnt_match(self):
        self.assertNotRegex("/alias @ops", re.compile(create_webhook_pattern("@ops")))

    def test_match_other_slash_command(self):
        self.assertRegex("/avocado @ops", re.compile(create_webhook_pattern("@ops")))

