"""
This module contains the example drivers for applications of the sample MacroParse grammars also found
herein. They are exercised in the testing framework.

One way or another, it's necessary to bind the messages of a definition to a set of functions and their
shared context per-scan/parse. The way that seems most natural in Python is to let a class definition
provide the implementation for the messages named in the scanner and parser specifications.

If the Python method names are kept distinct (as by using a different prefix for scan and parse actions)
then the same object can provide a sensible context and driver for both scanning and parsing. This
greatly facilitates any sort of context-dependent ad-hockery that your subject language might demand.

The expectation for parse reductions is natural and obvious: These are functions from a selection of
semantic-values to a newer, larger semantic value. The arguments and return values correspond to these.
"""

from boozetools import interfaces

# JSON -- Scanner:

class ScanJSON:
	"""
	This is the application driver for the JSON sample.
	As you can see, it contains methods named for the messages in the scanner definition.
	Returned values are yielded from the generic scanner algorithm, just as with MiniScan.
	A generic parser function consumes directly from such a stream.
	This simple approach to scanner/parser integration is usually just fine. Still,
	it's nice to be able to invert that relation and explicitly send tokens into the parser
	when and where you desire. To that end, a parser-as-object is in the pipeline.
	
	In most applications, the set of necessarily-distinct scanner recognition rules is likely to be
	relatively small, especially considering that the parse algorithm takes terminal identities symbolically.
	That is why the scanner messages come with room for a parameter. It just happens not to be particularly
	relevant for JSON, so the parameter is never actually used in this example.
	"""
	
	RESERVED = {'true': True, 'false':False, 'null':None}
	ESCAPES = {'b': 8, 't': 9, 'n': 10, 'f': 12, 'r': 13, }
	
	def on_ignore_whitespace(self, yy:interfaces.ScanState, parameter): pass
	def on_punctuation(self, yy:interfaces.ScanState, parameter): return yy.matched_text(), None
	def on_integer(self, yy:interfaces.ScanState, parameter): return 'number', int(yy.matched_text())
	def on_float(self, yy:interfaces.ScanState, parameter): return 'number', float(yy.matched_text())
	def on_reserved_word(self, yy:interfaces.ScanState, parameter): return yy.matched_text(), self.RESERVED[yy.matched_text()]
	def on_enter_string(self, yy:interfaces.ScanState, parameter):
		yy.enter('in_string')
		return yy.matched_text(), None
	def on_stringy_bit(self, yy:interfaces.ScanState, parameter): return 'character', yy.matched_text()
	def on_escaped_literal(self, yy:interfaces.ScanState, parameter): return 'character', yy.matched_text()[1]
	def on_shorthand_escape(self, yy:interfaces.ScanState, parameter): return 'character', chr(self.ESCAPES[yy.matched_text()[1]])
	def on_unicode_escape(self, yy:interfaces.ScanState, parameter): return 'character', chr(int(yy.matched_text()[2:],16))
	def on_leave_string(self, yy:interfaces.ScanState, parameter):
		yy.enter('INITIAL')
		return yy.matched_text(), None
	

# JSON -- Parser:
