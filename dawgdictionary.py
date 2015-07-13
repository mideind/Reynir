"""
    Reynir: Natural language processing for Icelandic

    Compound word analyzer

    Author: Vilhjalmur Thorsteinsson

    This software is at a very early development stage.
    While that is the case, it is:
    Copyright (c) 2015 Vilhjalmur Thorsteinsson
    All rights reserved
    See the accompanying README.md file for further licensing and copyright information.

    The compound word analyzer takes a word not found in the
    BIN word database and attempts to resolve it into parts
    as a compound word.

    It uses a Directed Acyclic Word Graph (DAWG) internally
    to store a large set of words in an efficient structure in terms
    of storage and speed.

    The graph is pre-built and stored in a pickled file that
    is loaded at run-time by DawgDictionary.

"""

import os
import threading
import logging
import time
import pickle


class _Node:

    """ This class must be at module level for pickling """

    def __init__(self):
        self.final = False
        self.edges = dict()


class DawgDictionary:

    def __init__(self):
        # Initialize an empty graph
        # The root entry will eventually be self._nodes[0]
        self._nodes = None
        # Running counter of nodes read
        self._index = 1
        # Lock to ensure that only one thread loads the dictionary
        self._lock = threading.Lock()

    def load_pickle(self, fname):
        """ Load a DAWG from a Python pickle file """
        with self._lock:
            if self._nodes is not None:
                # Already loaded
                return
            with open(fname, "rb") as pf:
                self._nodes = pickle.load(pf)

    def num_nodes(self):
        """ Return a count of unique nodes in the DAWG """
        return 0 if self._nodes is None else len(self._nodes)

    def find(self, word):
        """ Look for a word in the graph, returning True if it is found or False if not """
        nav = FindNavigator(word)
        self.navigate(nav)
        return nav.is_found()

    def __contains__(self, word):
        """ Enable simple lookup syntax: "word" in dawgdict """
        return self.find(word)

    def find_matches(self, pattern, sort=True):
        """ Returns a list of words matching a pattern.
            The pattern contains characters and '?'-signs denoting wildcards.
            Characters are matched exactly, while the wildcards match any character.
        """
        nav = MatchNavigator(pattern, sort)
        self.navigate(nav)
        return nav.result()

    def find_permutations(self, rack, minlen = 0):
        """ Returns a list of legal permutations of a rack of letters.
            The list is sorted in descending order by permutation length.
            The rack may contain question marks '?' as wildcards, matching all letters.
            Question marks should be used carefully as they can
            yield very large result sets.
        """
        nav = PermutationNavigator(rack, minlen)
        self.navigate(nav)
        return nav.result()

    def slice_compound_word(self, word):
        """ Attempt to slice an unknown word into parts, where each part is
            a valid word form in itself, and the parts form a valid compound word. """
        nav = CompoundNavigator(self, word)
        self.navigate(nav)
        w = nav.result()
        # We get back a list of lists, i.e. all possible compound word combinations
        # where each combination is a list of word parts. We return
        # the combination with the longest last part and the shortest overall
        # number of parts.
        w.sort(key = lambda x : (len(x[-1]), -len(x)))
        return w[-1] if w else None

    def navigate(self, nav):
        """ A generic function to navigate through the DAWG under
            the control of a navigation object.

            The navigation object should implement the following interface:

            def push_edge(firstchar)
                returns True if the edge should be entered or False if not
            def accepting()
                returns False if the navigator does not want more characters
            def accepts(newchar)
                returns True if the navigator will accept and 'eat' the new character
            def accept(matched, final)
                called to inform the navigator of a match and whether it is a final word
            def pop_edge()
                called when leaving an edge that has been navigated; returns False
                if there is no need to visit other edges
            def done()
                called when the navigation is completed
        """
        if self._nodes is None:
            # No graph: no navigation
            nav.done()
            return
        root = self._nodes[0] # Start at the root
        Navigation(nav).go(root)


class Wordbase:

    """ Container for two singleton instances of the word database,
        one for the main dictionary and the other for common words
    """

    _dawg = None
    _dawg_common = None

    _lock = threading.Lock()
    _lock_common = threading.Lock()

    @staticmethod
    def _load_resource(resource):
        """ Load a DawgDictionary, from either a text file or a pickle file """
        # Assumes that the appropriate lock has been acquired
        pname = os.path.abspath(os.path.join("resources", resource + ".dawg.pickle"))
        try:
            pname_t = os.path.getmtime(pname)
        except os.error:
            pname_t = None

        dawg = DawgDictionary()

        t0 = time.time()
        dawg.load_pickle(pname)
        t1 = time.time()
        logging.info(u"Loaded {0} graph nodes in {1:.2f} seconds".format(dawg.num_nodes(), t1 - t0))

        # Do not assign Wordbase._dawg until fully loaded, to prevent race conditions
        return dawg

    @staticmethod
    def _load():
        """ Load a main dictionary """
        with Wordbase._lock:
            if Wordbase._dawg is not None:
                # Already loaded: nothing to do
                return Wordbase._dawg
            return Wordbase._load_resource("ordalisti") # Main dictionary

    @staticmethod
    def dawg():
        """ Return the main dictionary DAWG object, loading it if required """
        if Wordbase._dawg is None:
            Wordbase._dawg = Wordbase._load()
        assert Wordbase._dawg is not None
        return Wordbase._dawg


class Navigation:

    """ Manages the state for a navigation while it is in progress """

    def __init__(self, nav):
        self._nav = nav
        # If the navigator has a method called accept_resumable(),
        # note it and call it with additional state information instead of
        # plain accept()
        self._resumable = callable(getattr(nav, "accept_resumable", None))

    def _navigate_from_node(self, node, matched):
        """ Starting from a given node, navigate outgoing edges """
        # Go through the edges of this node and follow the ones
        # okayed by the navigator
        for prefix, nextnode in node.edges.items():
            if self._nav.push_edge(prefix[0]):
                # This edge is a candidate: navigate through it
                self._navigate_from_edge(prefix, nextnode, matched)
                if not self._nav.pop_edge():
                    # Short-circuit and finish the loop if pop_edge() returns False
                    break

    def _navigate_from_edge(self, prefix, nextnode, matched):
        """ Navigate along an edge, accepting partial and full matches """
        # Go along the edge as long as the navigator is accepting
        lenp = len(prefix)
        j = 0
        while j < lenp and self._nav.accepting():
            # See if the navigator is OK with accepting the current character
            if not self._nav.accepts(prefix[j]):
                # Nope: we're done with this edge
                return
            # So far, we have a match: add a letter to the matched path
            matched += prefix[j]
            j += 1
            # Check whether the next prefix character is a vertical bar, denoting finality
            final = False
            if j < lenp and prefix[j] == u'|':
                final = True
                j += 1
            elif (j >= lenp) and ((nextnode is None) or nextnode.final):
                # If we're at the final char of the prefix and the next node is final,
                # set the final flag as well (there is no trailing vertical bar in this case)
                final = True
            # Tell the navigator where we are
            if self._resumable:
                # The navigator wants to know the position in the graph
                # so that navigation can be resumed later from this spot
                self._nav.accept_resumable(prefix[j:], nextnode, matched)
            else:
                # Normal navigator: tell it about the match
                self._nav.accept(matched, final)
        # We're done following the prefix for as long as it goes and
        # as long as the navigator was accepting
        if j < lenp:
            # We didn't complete the prefix, so the navigator must no longer
            # be interested (accepting): we're done
            return
        if self._nav.accepting() and (nextnode is not None):
            # Gone through the entire edge and still have rack letters left:
            # continue with the next node
            self._navigate_from_node(nextnode, matched)

    def go(self, root):
        """ Perform the navigation using the given navigator """
        if root is None:
            # No root: no navigation
            self._nav.done()
            return
        # The ship is ready to go
        if self._nav.accepting():
            # Leave shore and navigate the open seas
            self._navigate_from_node(root, u'')
        self._nav.done()

    def resume(self, prefix, nextnode, matched):
        """ Resume navigation from a previously saved state """
        self._navigate_from_edge(prefix, nextnode, matched)


class FindNavigator:

    """ A navigation class to be used with DawgDictionary.navigate()
        to find a particular word in the dictionary by exact match
    """

    def __init__(self, word):
        self._word = word
        self._len = len(word)
        self._index = 0
        self._found = False

    def push_edge(self, firstchar):
        """ Returns True if the edge should be entered or False if not """
        # Enter the edge if it fits where we are in the word
        return self._word[self._index] == firstchar

    def accepting(self):
        """ Returns False if the navigator does not want more characters """
        # Don't go too deep
        return self._index < self._len

    def accepts(self, newchar):
        """ Returns True if the navigator will accept the new character """
        if newchar != self._word[self._index]:
            return False
        # Match: move to the next index position
        self._index += 1
        return True

    def accept(self, matched, final):
        """ Called to inform the navigator of a match and whether it is a final word """
        if final and self._index == self._len:
            # Yes, this is what we were looking for
            assert matched == self._word
            self._found = True

    def pop_edge(self):
        """ Called when leaving an edge that has been navigated """
        # We only need to visit one outgoing edge, so short-circuit the edge loop
        return False

    def done(self):
        """ Called when the whole navigation is done """
        pass

    def is_found(self):
        return self._found


class PermutationNavigator:

    """ A navigation class to be used with DawgDictionary.navigate()
        to find all permutations of a rack
    """

    def __init__(self, rack, minlen = 0):
        self._rack = rack
        self._stack = []
        self._result = []
        self._minlen = minlen

    def push_edge(self, firstchar):
        """ Returns True if the edge should be entered or False if not """
        # Follow all edges that match a letter in the rack
        # (which can be '?', matching all edges)
        if not ((firstchar in self._rack) or (u'?' in self._rack)):
            return False
        # Fit: save our rack and move into the edge
        self._stack.append(self._rack)
        return True

    def accepting(self):
        """ Returns False if the navigator does not want more characters """
        # Continue as long as there is something left on the rack
        return bool(self._rack)

    def accepts(self, newchar):
        """ Returns True if the navigator will accept the new character """
        exactmatch = newchar in self._rack
        if (not exactmatch) and (u'?' not in self._rack):
            # Can't continue with this prefix - we no longer have rack letters matching it
            return False
        # We're fine with this: accept the character and remove from the rack
        if exactmatch:
            self._rack = self._rack.replace(newchar, u'', 1)
        else:
            self._rack = self._rack.replace(u'?', u'', 1)
        return True

    def accept(self, matched, final):
        """ Called to inform the navigator of a match and whether it is a final word """
        if final and len(matched) >= self._minlen:
            self._result.append(matched)

    def pop_edge(self):
        """ Called when leaving an edge that has been navigated """
        self._rack = self._stack.pop()
        # We need to visit all outgoing edges, so return True
        return True

    def done(self):
        """ Called when the whole navigation is done """
        pass

    def result(self):
        return self._result


class MatchNavigator:

    """ A navigation class to be used with DawgDictionary.navigate()
        to find all words matching a pattern
    """

    def __init__(self, pattern):
        self._pattern = pattern
        self._lenp = len(pattern)
        self._index = 0
        self._chmatch = pattern[0]
        self._wildcard = (self._chmatch == u'?')
        self._stack = []
        self._result = []

    def push_edge(self, firstchar):
        """ Returns True if the edge should be entered or False if not """
        # Follow all edges that match a letter in the rack
        # (which can be '?', matching all edges)
        if not self._wildcard and (firstchar != self._chmatch):
            return False
        # Fit: save our index and move into the edge
        self._stack.append((self._index, self._chmatch, self._wildcard))
        return True

    def accepting(self):
        """ Returns False if the navigator does not want more characters """
        # Continue as long as there is something left to match
        return self._index < self._lenp

    def accepts(self, newchar):
        """ Returns True if the navigator will accept the new character """
        if not self._wildcard and (newchar != self._chmatch):
            return False
        self._index += 1
        if self._index < self._lenp:
            self._chmatch = self._pattern[self._index]
            self._wildcard = (self._chmatch == u'?')
        return True

    def accept(self, matched, final):
        """ Called to inform the navigator of a match and whether it is a final word """
        if final and self._index == self._lenp:
            # We have an entire pattern match
            # (Note that this could be relaxed to also return partial (shorter) pattern matches)
            self._result.append(matched)

    def pop_edge(self):
        """ Called when leaving an edge that has been navigated """
        self._index, self._chmatch, self._wildcard = self._stack.pop()
        # We need to continue visiting edges only if this is a wildcard position
        return self._wildcard

    def done(self):
        """ Called when the whole navigation is done """
        pass

    def result(self):
        return self._result


class CompoundNavigator:

    """ A navigation class to be used with DawgDictionary.navigate()
        to find all possible compositions of shorter words that
        together form a long (compound) word.
    """

    def __init__(self, dawg, word):
        self._dawg = dawg
        self._word = word
        self._len = len(word)
        self._index = 0
        self._parts = []

    def push_edge(self, firstchar):
        """ Returns True if the edge should be entered or False if not """
        # Follow all edges that match a letter in the rack
        # (which can be '?', matching all edges)
        return self._word[self._index] == firstchar

    def accepting(self):
        """ Returns False if the navigator does not want more characters """
        # Continue until we have generated all left parts possible from the
        # rack but leaving at least one tile
        return self._index < self._len

    def accepts(self, newchar):
        """ Returns True if the navigator will accept the new character """
        if newchar != self._word[self._index]:
            return False
        self._index += 1
        return True

    def accept(self, matched, final):
        """ Called to inform the navigator of a match and whether it is a final word """
        if final:
            # We have a valid word so far: attempt to resolve the following text
            if self._index == self._len:
                # Complete match: return a single part
                self._parts = [ [ matched ] ]
            else:
                # So far so good: try to match the rest
                nav = CompoundNavigator(self._dawg, self._word[self._index:])
                self._dawg.navigate(nav)
                result = nav.result()
                self._parts.extend( [ [ matched ] + tail for tail in result ] )

    def pop_edge(self):
        """ Called when leaving an edge that has been navigated """
        return False

    def done(self):
        """ Called when the whole navigation is done """
        pass

    def result(self):
        return self._parts
