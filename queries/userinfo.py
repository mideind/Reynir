"""

    Greynir: Natural language processing for Icelandic

    Distance query response module

    Copyright (C) 2020 Miðeind ehf.

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


    This module generates a polite introductory response to statements
    of the form "Ég heiti X" ("My name is X").

"""

import re

from reynir.bindb import BIN_Db

from geo import icelandic_addr_info, iceprep_for_placename
from query import Query
from . import gen_answer, numbers_to_neutral


_USERINFO_QTYPE = "UserInfo"


_WHO_IS_ME = "hver er {0}"
_YOU_ARE = "Þú, kæri notandi, heitir {0}"


def _whoisme_handler(q: Query, ql: str) -> bool:
    """ Handle queries of the form "Hver er [nafn notanda]?" """
    nd = q.client_data("name")
    if not nd:
        return False

    for t in ["first", "full"]:
        if t not in nd:
            continue
        if ql == _WHO_IS_ME.format(nd[t].lower()):
            q.set_answer(*gen_answer(_YOU_ARE.format(nd[t])))
            return True

    return False


_WHATS_MY_NAME = frozenset(
    (
        "hvað heiti ég fullu nafni",
        "hvað heiti ég",
        "veistu hvað ég heiti",
        "veistu hvað ég heiti fullu nafni",
        "veist þú hvað ég heiti",
        "veist þú hvað ég heiti fullu nafni",
        "veistu ekki hvað ég heiti",
        "veist þú ekki hvað ég heiti",
        "hver er ég",
        "veistu hver ég er",
        "veistu ekki hver ég er",
        "veist þú hver ég er",
        "veist þú ekki hver ég er",
        "hvaða nafn er ég með",
        "hvaða nafni heiti ég",
        "veistu hvaða nafni ég heiti",
        "hvað heiti ég eiginlega",
        "hvaða nafn ber ég",
    )
)


_DUNNO_NAME = "Ég veit ekki hvað þú heitir, en þú getur sagt mér það."


def _whatsmyname_handler(q: Query, ql: str) -> bool:
    """ Handle queries of the form "Hvað heiti ég?" """
    if ql in _WHATS_MY_NAME:
        answ = None
        nd = q.client_data("name")
        if nd and "full" in nd:
            answ = f"Þú heitir {nd['full']}"
        elif nd and "first" in nd:
            answ = f"Þú heitir {nd['first']}"
        else:
            answ = _DUNNO_NAME
        q.set_answer(*gen_answer(answ))
        return True


_MY_NAME_IS_REGEXES = frozenset(
    (
        r"^ég heiti (.+)$",
        r"^nafn mitt er (.+)$",
        r"^nafnið mitt er (.+)$",
        r"^ég ber heitið (.+)$",
        r"^ég ber nafnið (.+)$",
    )
)

_INTRODUCTION_RESPONSES = {
    "hk": "Gaman að kynnast þér, {0}. Ég heiti Embla.",
    "kk": "Sæll og blessaður, {0}. Ég heiti Embla.",
    "kvk": "Sæl og blessuð, {0}. Ég heiti Embla.",
}


def _mynameis_handler(q: Query, ql: str) -> bool:
    """ Handle queries of the form "Ég heiti X", store this information. """
    for rx in _MY_NAME_IS_REGEXES:
        m = re.search(rx, ql)
        if m:
            break
    if m:
        name = m.group(1).strip()
        # TODO: Strip any non alphabetic chars?
        if not name:
            return False

        # Get first name, look up gender for a gender-tailored response
        with BIN_Db.get_db() as bdb:
            fn = name.split()[0].title()
            gender = bdb.lookup_name_gender(fn) or "hk"
            answ = _INTRODUCTION_RESPONSES[gender].format(fn)

        # Save this info about user to query data table
        if q.client_id:
            qdata = dict(full=name.title(), first=fn, gender=gender)
            q.set_client_data("name", qdata)

        # Generate answer
        voice = answ.replace(",", "")
        q.set_answer(dict(answer=answ), answ, voice)
        q.query_is_command()
        return True

    return False


_WHATS_MY_ADDR = frozenset(
    (
        "hvar á ég heima",
        "hvar á ég eiginlega heima",
        "veistu hvar ég á heima",
        "veist þú hvar ég á heima",
        "hvar bý ég",
        "hvar bý ég eiginlega",
        "veistu hvar ég bý",
        "veist þú hvar ég bý",
        "hvað er heimilisfang mitt",
        "hvað er heimilisfangið mitt",
        "hvert er heimilisfang mitt",
        "hvert er heimilisfangið mitt",
    )
)


def _whatsmyaddr_handler(q: Query, ql: str) -> bool:
    """ Handle queries of the form "Hvar á ég heima?" """
    pass


_MY_ADDRESS_REGEXES = (
    r"ég á heima á (.+)$",
    r"ég á heima í (.+)$",
    r"heimilisfang mitt er á (.+)$",
    r"heimilisfang mitt er í (.+)$",
    r"heimilisfang mitt er (.+)$",
)

_DUNNO_ADDRESS = "Ég veit ekki hvar þú átt heima, en þú getur sagt mér það."
_ADDR_LOOKUP_FAIL = "Ekki tókst að fletta upp þessu heimilisfangi."


def _myaddris_handler(q: Query, ql: str) -> bool:
    """ Handle queries of the form "Ég á heima á [heimilisfang]".
        Store this info as query data. """
    for rx in _MY_ADDRESS_REGEXES:
        m = re.search(rx, ql)
        if m:
            break
    if not m:
        return False

    addr_str = m.group(1).strip()
    if not addr_str:
        return False

    # Try to parse address, e.g. "Öldugötu 4 [í Reykjavík]"
    m = re.search(r"^(\w+)\s(\d+)\s?([í|á]\s)?(\w+)?$", addr_str.strip())
    if not m:
        q.set_answer(*gen_answer(_ADDR_LOOKUP_FAIL))
        return True

    # Matches a reasonable address
    groups = m.groups()
    (street, num) = (groups[0], groups[1])
    placename = None
    if len(groups) == 3 and groups[2] not in ["í", "á"]:
        placename = groups[2]
    elif len(groups) == 4:
        placename = groups[3]

    # Look up info about address
    addrfmt = f"{street} {num}"
    addrinfo = icelandic_addr_info(addrfmt, placename=placename)

    if not addrinfo:
        q.set_answer(*gen_answer(_ADDR_LOOKUP_FAIL))
        return True

    # Save this info about user to query data table
    if q.client_id:
        d = {
            "street": addrinfo["heiti_nf"],
            "number": addrinfo["husnr"],
            "lat": addrinfo["lat_wgs84"],
            "lon": addrinfo["long_wgs84"],
            "placename": addrinfo["stadur_nf"],
            "area": addrinfo["svaedi_nf"],
        }
        q.set_client_data("address", d)

        # Generate answer
        prep = iceprep_for_placename(d["placename"])
        answ = "Heimilisfang þitt hefur verið skráð sem {0} {1} {2} {3}".format(
            d["street"], numbers_to_neutral(str(d["number"])), prep, d["placename"]
        )
        q.set_answer(*gen_answer(answ))
    else:
        q.set_answer(*gen_answer("Ekki tókst að vista heimilisfang. Auðkenni vantar."))

    return True


def _whatsmynum_handler(q: Query, ql: str) -> bool:
    """ Handle queries of the form "Hvað er símanúmerið mitt? """
    pass


_MY_PHONE_IS_REGEXES = (
    r"símanúmer mitt er (.+)$",
    r"símanúmerið mitt er (.+)$",
    r"ég er með símanúmer (.+)$",
    r"ég er með símanúmerið (.+)$",
)


_DUNNO_PHONE_NUM = "Ég veit ekki hvert símanúmer þitt er, en þú getur sagt mér það."


def _mynumis_handler(q: Query, ql: str) -> bool:
    """ Handle queries of the form "Hvað er símanúmerið mitt? """
    pass


# Handler functions for all query types supported by this module.
_HANDLERS = [
    _whoisme_handler,
    _whatsmyname_handler,
    _mynameis_handler,
    # _whatsmyaddr_handler,
    _myaddris_handler,
    # _whatsmynum_handler,
    # _mynumis_handler,
]


def handle_plain_text(q: Query) -> bool:
    """ Handle plain text query. """
    ql = q.query_lower.rstrip("?")

    # Iterate over all handlers, see if any
    # of them wants to handle the query
    for h in _HANDLERS:
        handled = h(q, ql)
        if handled:
            q.set_qtype(_USERINFO_QTYPE)
            return True

    return False
