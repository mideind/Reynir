"""

    Reynir: Natural language processing for Icelandic

    Bus schedule query module

    Copyright (C) 2019 Miðeind ehf.
    Original author: Vilhjálmur Þorsteinsson

       This program is free software: you can redistribute it and/or modify
       it under the terms of the GNU General Public License as published by
       the Free Software Foundation, either version 3 of the License, or
       (at your option) any later version.
       This program is distributed in the hope that it will be useful,
       but WITHOUT ANY WARRANTY; without even the implied warranty of
       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
       GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see http://www.gnu.org/licenses/.


    This module implements a processor for queries about bus schedules.

"""


# Indicate that this module wants to handle parse trees for queries,
# as opposed to simple literal text strings
HANDLE_TREE = True

# The context-free grammar for the queries recognized by this plug-in module
GRAMMAR = """

# ----------------------------------------------
#
# Query grammar for bus-related queries
#
# ----------------------------------------------

# A plug-in query grammar always starts with the following,
# adding one or more query productions to the Queries nonterminal

Queries →
    QBusArrivalTime

QBusArrivalTime →
    # 'Hvenær kemur ásinn/sexan/tían/strætó númer tvö?'
    "hvenær" "kemur" QBus_nf '?'?
    # 'Hvenær er von á fimmunni / vagni númer sex?'
    | "hvenær" "er" "von" "á" QBus_þgf '?'?
    # 'Hvenær má búast við leið þrettán?
    | "hvenær" "má" "búast" "við" QBus_þgf '?'?

# We can specify a bus in different ways, which may require
# the bus identifier to be in different cases

QBus/fall →
    QBusWord/fall | QBusNumber/fall

QBusWord/fall →
    'ás:kk'_et_gr/fall
    | 'tvistur:kk'_et_gr/fall
    | 'þristur:kk'_et_gr/fall
    | 'fjarki:kk'_et_gr/fall
    | 'fimma:kvk'_et_gr/fall
    | 'sexa:kvk'_et_gr/fall
    | 'sjöa:kvk'_et_gr/fall
    | 'átta:kvk'_et_gr/fall
    | 'nía:kvk'_et_gr/fall
    | 'tía:kvk'_et_gr/fall
    | 'tólfa:kvk'_et_gr/fall

QBusNumber/fall →
    'leið:kvk'_et/fall 'númer:hk'_et_nf? QBusNumberWord
    | 'strætó:kk'_et/fall 'númer:hk'_et_nf QBusNumberWord
    | 'vagn:kk'_et/fall 'númer:hk'_et_nf QBusNumberWord

QBusNumberWord →
    "eitt" | to_nf_ft_hk | töl

"""


# The following functions correspond to grammar nonterminals (see
# the context-free grammar above, in GRAMMAR) and are called during
# tree processing (depth-first, i.e. bottom-up navigation).


def QBusArrivalTime(node, params, result):
    """ Bus arrival time query """
    # Set the query type
    result.qtype = "ArrivalTime"
    if "bus_number" in result:
        # Set the query key
        result.qkey = result.bus_number


def QBus(node, params, result):
    pass


_BUS_WORDS = {
    "ás": 1,
    "tvistur": 2,
    "þristur": 3,
    "fjarki": 4,
    "fimma": 5,
    "sexa": 6,
    "sjöa": 7,
    "átta": 8,
    "nía": 9,
    "tía": 10,
    "tólfa": 12,
    "einn": 1,
    "tveir": 2,
    "þrír": 3,
    "fjórir": 4,
    "fimm": 5,
    "sex": 6,
    "sjö": 7,
    "níu": 9,
    "tíu": 10,
    "ellefu": 11,
    "tólf": 12,
    "þrettán": 13,
    "fjórtán": 14,
    "fimmtán": 15,
    "sextán": 16,
    "sautján": 17,
    "átján": 18,
    "nítján": 19,
    "tuttugu": 20,
    "þrjátíu": 30,
    "fjörutíu": 40,
    "fimmtíu": 50,
    "sextíu": 60,
    "sjötíu": 70,
    "áttatíu": 80,
    "níutíu": 90,
}


def QBusWord(node, params, result):
    result.bus_name = result._nominative
    result.bus_number = _BUS_WORDS.get(result._canonical, 0)
    print("Translated bus number {0} to {1}".format(result._canonical, result.bus_number))
    print("_nominative is {0}, _indefinite is {1}".format(result._nominative, result._indefinite))


def QBusNumber(node, params, result):
    result.bus_name = result._nominative


def QBusNumberWord(node, params, result):
    result.bus_number = _BUS_WORDS.get(result._canonical, 0)
    print("Translated bus number {0} to {1}".format(result._canonical, result.bus_number))
    print("_nominative is {0}, _indefinite is {1}".format(result._nominative, result._indefinite))


# End of grammar nonterminal handlers

# The function below answers queries about bus arrival times

def query_arrival_time(query, session, bus_number, bus_name):
    """ A query for a bus arrival time """
    response = dict(answer="15:33")
    voice_answer = bus_name[0].upper() + bus_name[1:] + " kemur klukkan 15 33"
    return response, voice_answer


# Dispatcher for the various query types implemented in this module
_QFUNC = {
    "ArrivalTime": query_arrival_time,
}

# The following function is called after processing the parse
# tree for a query sentence that is handled in this module

def sentence(state, result):
    """ Called when sentence processing is complete """
    q = state["query"]
    if "qtype" in result:
        # Successfully matched a query type
        q.set_qtype(result.qtype)
        q.set_key(result.qkey)
        session = state["session"]
        # Select a query function and exceute it
        qfunc = _QFUNC.get(result.qtype)
        if qfunc is None:
            q.set_answer(result.qtype + ": " + result.qkey)
        else:
            try:
                voice_answer = None
                answer = qfunc(q, session, result.bus_number, result.bus_name)
                if isinstance(answer, tuple):
                    # We have both a normal and a voice answer
                    answer, voice_answer = answer
                q.set_answer(answer, voice_answer)
            except AssertionError:
                raise
            except Exception as e:
                q.set_error("E_EXCEPTION: {0}".format(e))
    else:
        q.set_error("E_QUERY_NOT_UNDERSTOOD")