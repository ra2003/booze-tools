"""
Attributed context-free grammar with operator-precedence and associativity declarations.

This file is basically all about the data structure, with relatively little intrinsic
functionality beyond simple queries. That's because the kinds of work people might do
to a model of a grammar extends far beyond the specific applications here included.
"""

import collections, itertools
from typing import List, Optional, NamedTuple, Hashable, Sequence
from ..support import foundation, pretty

LEFT, RIGHT, NONASSOC, BOGUS = object(), object(), object(), object()

class Fault(ValueError): pass
class DuplicateRule(Fault): pass
class NonTerminalsCannotHavePrecedence(Fault): pass
class FailedToSetPrecedenceOnPrecsym(Fault): pass
class PrecedenceDeclaredTwice(Fault): pass
class RuleProducesBogusToken(Fault): pass # The rule produces a bogus symbol...
class UnreachableSymbols(Fault): pass
class IllFoundedSymbols(Fault): pass
class RenamingLoop(Fault): pass
class EpsilonLoop(Fault): pass

class ContextFreeGrammar:
	"""
	Formally, a context free grammar consists of:
		* A set of terminal symbols,
		* A set of non-terminal symbols, disjoint from the terminals,
		* A set of production rules (as described at class Rule),
		* and a start symbol.
	
	As a cool and potentially useful hack, I expand the normal definition to allow
	potentially several "start symbols" to share the same overall definition. This allows
	a single set of tables to be used (with a different initial state) to parse different
	languages (or sub-phrases) while sharing common specification elements.
	
	Practical languages usually have some ambiguities which are ordinarily resolved with
	precedence declarations. If explicit declarations are not provided, the grammar is
	ambiguous -- at least with respect to the power of the table-generation method used.
	There are ways to deal with ambiguity, but for deterministic parsers the convention
	is to shift on a shift-reduce conflict (i.e. assume right-associativity) and, in
	the event of a reduce/reduce conflict, to use the earliest-defined rule.
	"""
	def __init__(self):
		self.symbols = set()
		self.start = [] # The start symbol(s) may be specified asynchronously to construction or the rules.
		self.rules, self.token_precedence, self.level_assoc = [], {}, []
		self.symbol_rule_ids = {}
	def display(self):
		head = ['', 'Symbol', 'Produces', 'Using']
		body = [[i, rule.lhs, rule.rhs, rule.attribute] for i,rule in enumerate(self.rules)]
		pretty.print_grid([head] + body)

	def rule(self, lhs:str, rhs:List[str], prec_sym, constructor:Hashable, places:(list, tuple, int), origin):
		"""
		This is your basic mechanism to install arbitrary plain-jane BNF rules.
		It provides the consistency checks better than if you were to instantiate Rule directly.
		
		For the sake of simplicity, at this layer symbols are all strings.
		Duplicate rules are rejected by raising an exception.
		
		:param lhs: The "left-hand-side" non-terminal symbol which is declared to produce...
		
		:param rhs: this "right-hand-side" sequence of symbols.
		
		:param prec_sym: Set the precedence of this reduction explicitly according to that
		of the given symbol as previously declared. If this is not supplied and the table
		construction algorithm finds it necessary, method infer_prec_sym(...) implements
		default processing on the right-hand-side.
		
		:param constructor: and
		:param places: designate the semantics for the attribute synthesis portion of the
		rule specification. If `constructor` is `None`, then places is expected to be the
		significant-symbol index into the RHS for a renaming or bracketing rule. Otherwise,
		`places` should be a list/tuple of such indices relevant to the given constructor.
		Note: At this level we don't interpret constructors further.
		
		Note: unit/renaming productions are recognized, and the parser tables will optimize
		such rules to a zero-cost abstraction wherever possible.
		
		:param origin: Use this to indicate the provenance of the rule. It can be a source
		line number, or whatever else makes sense in your application.
		
		:return: Nothing.
		
		Please note: Certain rare constructions make the unit-rule optimization unsound.
		The tables will be constructed correctly but the general parsing algorithm needs
		to be prepared to find a rule with a null attribute. Correct behavior is generally
		to leave the semantic-stack unchanged.
		"""
		if lhs in self.token_precedence: raise NonTerminalsCannotHavePrecedence(lhs)
		self.symbols.add(lhs)
		self.symbols.update(rhs)
		if lhs not in self.symbol_rule_ids: self.symbol_rule_ids[lhs] = []
		if isinstance(places, int): assert constructor is None and 0 <= places < len(rhs)
		else: assert isinstance(places, (list, tuple)) and all(p<len(rhs) for p in places), places
		sri = self.symbol_rule_ids[lhs]
		if any(self.rules[rule_id].rhs == rhs for rule_id in sri): raise DuplicateRule(lhs, rhs)
		sri.append(foundation.allocate(self.rules, Rule(lhs, rhs, prec_sym, constructor, places, origin)))
	
	def augmented_rules(self) -> list:
		"""
		The LR family of algorithms are normally explained in terms of an augmented grammar:
		It has a special "accept" rule which just expands to the start symbol for the ordinary
		context-free grammar at issue. There's a good reason for this: It makes the algorithms
		work properly without a lot of special edge cases to worry about. However, the "accept"
		non-terminal ought to be imaginary: it can't appear on the right, one never reduces the
		"accept" symbol, and I object to it consuming space in the GOTO table as it typically
		does in implementations that rely on a first-class rule (with left-hand side symbol).

		This object exists to clarify interaction with the "augmented" rule set.
		NB: Since we support multiple "start" symbols, there are corresponding "accept" rules.
		"""
		assert self.start
		return [rule.rhs for rule in self.rules] + [[language] for language in self.start]
	
	def initial(self) -> range:
		""" The range of augmented-rule indices corresponding to the list of start symbols. """
		first = len(self.rules)
		return range(first, first+len(self.start))
	
	def apparent_terminals(self) -> set:
		""" Of all symbols mentioned, those without production rules are apparently terminal. """
		return self.symbols - self.symbol_rule_ids.keys()

	def find_first_and_epsilon(self):
		"""
		Answers the two questions:
			Which terminals can symbol X begin with?
			Which symbols can produce the empty string?
		This solution takes pains not to repeat work, and so should be reasonably quick.
		"""
		epsilon = set()
		first = {s:{s} for s in self.symbols}
		hangar = collections.defaultdict(list)
		work = [(i,0) for i in range(len(self.rules))]
		while work:
			r,p = work.pop()
			lhs, rhs, _, _, _, _ = self.rules[r]
			if p == len(rhs):
				epsilon.add(lhs)
				if lhs in hangar: work.extend(hangar.pop(lhs))
			else:
				symbol = rhs[p]
				first[lhs].add(symbol)
				if symbol in epsilon: work.append((r,p+1))
				else: hangar[symbol].append((r,p+1))
		for component in foundation.strongly_connected_components_hashable(first):
			f = set()
			for symbol in component:
				f.update(*(first[x] for x in first[symbol]))
				first[symbol] = f
			f.difference_update(self.symbol_rule_ids)
		return first, epsilon
		
	def assert_no_bogons(self):
		""" "Bogus" tokens only exist to establish precedence levels and must not appear in right-hand sides. """
		bogons = {sym for sym, prec in self.token_precedence.items() if self.level_assoc[prec] is BOGUS}
		for rule_id, rule in enumerate(self.rules):
			if any(symbol in bogons for symbol in rule.rhs):
				raise RuleProducesBogusToken(rule_id)
	
	def assert_well_founded(self):
		"""
		Here, "well-founded" means "can possibly produce a finite sequence of terminals."
		"Ill-founded" is the opposite. Example ill-founded grammars:
			S -> x S
			A -> B y;  B -> A x
		
		A terminal symbol is well-founded.
		A rule with only well-founded symbols in the right-hand side is well-founded.
		A non-terminal symbol with at least one well-founded rule is well-founded.
		Induction applies. A grammar with only well-founded symbols is well-founded.
		"""
		well_founded = self.apparent_terminals()
		black = list(self.rules)
		while black:
			red = []
			for rule in black:
				if rule.lhs not in well_founded:
					if all(s in well_founded for s in rule.rhs): well_founded.add(rule.lhs)
					else: red.append(rule)
			if len(red) < len(black): black = red
			else: raise IllFoundedSymbols(set(rule.lhs for rule in red))
	
	def assert_no_orphans(self):
		""" Every symbol should be reachable from the start symbol(s). """
		produces = collections.defaultdict(set)
		for rule in self.rules: produces[rule.lhs].update(rule.rhs)
		unreachable = self.symbols - foundation.transitive_closure(self.start, produces.get)
		if unreachable: raise UnreachableSymbols(unreachable) # NB: Bogons are not among self.symbols.
	
	def assert_no_rename_loops(self):
		""" If a symbol may be replaced by itself (possibly indirectly) then it is diseased. """
		broken = set()
		renames = collections.defaultdict(set)
		for lhs, rhs, _, _, _, _ in self.rules:
			if len(rhs) == 1:
				if lhs == rhs[0]: broken.add(lhs)
				else: renames[lhs].add(rhs[0])
		for component in foundation.strongly_connected_components_hashable(renames):
			if len(component) > 1: broken.update(component)
		if broken: raise RenamingLoop(broken)
	
	def assert_no_epsilon_loops(self):
		""" Epsilon Left-Self-Recursion is OK. All other recursive-epsilon-loops are pathological. """
		first, epsilon = self.find_first_and_epsilon()
		reaches = collections.defaultdict(set)
		broken = set()
		for lhs, rhs, _, _, _, _ in self.rules:
			epsilon_prefix = list(itertools.takewhile(epsilon.__contains__, rhs))
			if not epsilon_prefix: continue
			if epsilon_prefix[0] == lhs: epsilon_prefix.pop(0)
			if lhs in epsilon_prefix: broken.add(lhs)
			reaches[lhs].update(epsilon_prefix)
		for component in foundation.strongly_connected_components_hashable(reaches):
			if len(component) > 1: broken.update(component)
		if broken: raise EpsilonLoop(broken)
		
	def validate(self):
		"""
		This raises an exception (derived from Fault, above) for the first error noticed.
		It might be nice to get a more complete read-out of problems, but that would mean
		inventing some sort of document structure to talk about faults in grammars.
		Then again, maybe that's in the pipeline.
		"""
		self.assert_no_bogons()
		self.assert_well_founded()
		self.assert_no_orphans()
		self.assert_no_rename_loops()
		self.assert_no_epsilon_loops()
	
	def assoc(self, direction, symbols):
		assert direction in (LEFT, NONASSOC, RIGHT, BOGUS)
		assert symbols
		level = foundation.allocate(self.level_assoc, direction)
		for symbol in symbols:
			if symbol in self.symbol_rule_ids: raise NonTerminalsCannotHavePrecedence(symbol)
			if symbol in self.token_precedence: raise PrecedenceDeclaredTwice(symbol)
			self.token_precedence[symbol] = level
			
	def decide_shift_reduce(self, symbol, rule_id):
		try: sp = self.token_precedence[symbol]
		except KeyError: return None
		rp = self.determine_rule_precedence(rule_id)
		if rp is None: return None
		if rp < sp: return LEFT
		# NB: Bison and Lemon both treat later declarations as higher-precedence,
		# which is unintuitive, in that you perform higher-precedence operations
		# first so it makes sense to list them first. Please excuse my dear aunt Sally!
		if rp == sp: return self.level_assoc[rp]
		return RIGHT
	
	def infer_prec_sym(self, rhs):
		"""
		If a rule without an explicit precedence declaration is involved in a shift/reduce conflict,
		the parse table generation algorithm will call this to decide which symbol represents the
		precedence of this right-hand-side.
		
		As a slight refinement to the BISON approach, this returns the first terminal with an
		assigned precedence, as opposed to the first terminal symbol whatsoever. Often that's
		a distinction without a difference, but when it matters I think this makes more sense.
		"""
		for symbol in rhs:
			if symbol in self.token_precedence:
				return symbol
	
	def determine_rule_precedence(self, rule_id):
		rule = self.rules[rule_id]
		prec_sym = rule.prec_sym or self.infer_prec_sym(rule.rhs)
		if prec_sym: return self.token_precedence[prec_sym]

class Rule(NamedTuple):
	# The first few fields define the actual grammar
	lhs: str
	rhs: List[str]
	prec_sym: Optional[str]
	# The next couple deal with the idea of attribute synthesis
	constructor: Hashable
	places: Sequence[int]
	# Last is all about the provenance of the rule, which is important in debugging.
	origin: object
	
	def is_rename(self):
		return self.constructor is None and len(self.rhs) == 1 and self.places == 0

