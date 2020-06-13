import asyncio
import datetime
import json
import os
import time
import txtorcon
import urllib.request
import requests
import sys
from peewee import chunked

from tqdm import tqdm
from twisted.internet import asyncioreactor
from twisted.internet.defer import ensureDeferred
from twisted.internet.endpoints import TCP4ClientEndpoint, UNIXClientEndpoint
from twisted.internet.task import react
import twisted
from itertools import product
import uuid
from random import shuffle
from time import sleep

from playhouse.db_url import parse as db_url_parse

from Measurement import OneCircuitMeasurement, TwoHopMeasurement, batch_one_circ_insert, batch_two_hop_insert, \
    getDatabase


async def launch_tor(reactor, instance):
    control_ep = UNIXClientEndpoint(reactor, f"/run/tor-instances/{instance}/control")
    tor = await txtorcon.connect(reactor, control_ep)
    config = await tor.get_config()
    state = await tor.create_state()
    socks = UNIXClientEndpoint(reactor, f"/run/tor-instances/{instance}/socks")
    return [tor, config, state, socks]


def prependToKey(name, dic):
    if name == "":
        return dic
    new_dic = {}
    for k, v in dic.items():
        new_dic[f"{name}_{k}"] = v
    return new_dic


async def build_circuit(config, path):
    circuit = None
    error = ""
    t_start = datetime.datetime.now()
    try:
        circuitDef = config['state'].build_circuit(routers=path, using_guards=False)
        circuit = await circuitDef
        d = circuit.when_built()
        d.addTimeout(10,config['reactor'])
        await d
        success = True
    except Exception as err:
        error = str(err)
        success = False
    t_stop = datetime.datetime.now()
    delta = getDeltaMilli(t_start,t_stop)
    return circuit, {"success": success,
                     "time":delta,
                     "error": error}


async def request_over_circuit(config, circuit):
    success = False
    error = ""
    t_start = datetime.datetime.now()
    try:
        agent = circuit.web_agent(config['reactor'], config['socks'])
        await agent.request(b'HEAD', config['url'])
        success = True
    except Exception as err:
        error = str(err)
        success = False
    t_stop = datetime.datetime.now()
    delta = getDeltaMilli(t_start,t_stop)
    return {"success": success,
            "time": delta,
            "error": error,
            "url": config['url']}


def gracefulClose(circuit):
    if circuit is None:
        return
    if circuit.is_built:
        try:
            circuit.close()
        except Exception as err:
            return


async def time_two_hop(config, guard, exit_node):
    timestamp = datetime.datetime.now()
    measurement = {"timestamp": timestamp,
                   "guard": guard.id_hex, #TODO Include more details
                   "exit": exit_node.id_hex}
    circuit, circuit_results = await build_circuit(config, [guard, exit_node])
    measurement.update(prependToKey("circuit", circuit_results))
    if circuit_results["circuit_success"]:
        request_results = await request_over_circuit(config, circuit)
        measurement.update(prependToKey("request", request_results))
    gracefulClose(circuit)
    return measurement


def getDeltaMilli(t1, t2):
    if t1 is None or t2 is None:
        return -1
    else:
        return int((t2 - t1).microseconds / 1000)


def get_gcp_metadata(key):
    session = requests.Session()
    proxies = {"http": None, "https": None}

    response = session.get(
        f'http://metadata.google.internal/computeMetadata/v1/instance/{key}',
        headers={'Metadata-Flavor': 'Google'},
        timeout=30, proxies=proxies)
    return response


async def test_two_hops(config, metadata, sources, exits):
    nr = len(sources)
    ne = len(exits)
    measurements = list()
    for relay, exit_node in tqdm(product(sources, exits), total=nr * ne, leave=False):
        result = await time_two_hop(config, relay, exit_node)
        result.update(metadata)
        measurements.append(TwoHopMeasurement(**result))
    batch_two_hop_insert(measurements, 200)
    print(f"Inserted {len(measurements)} two-hop measurements at {datetime.datetime.now()}")
    return True


async def test_one_circuit(config, metadata, targets, chunk_size=100):
    for chunk in chunked(targets, chunk_size):
        measurements = list()
        for t in tqdm(chunk, total=chunk_size, leave=False):
            timestamp = datetime.datetime.now()
            measurement = {"timestamp":timestamp,"target":t.id_hex} #TODO Include more details
            c, result = await build_circuit(config, [t])
            gracefulClose(c)
            measurement.update(prependToKey("circuit",result))
            measurement.update(metadata)
            measurements.append(OneCircuitMeasurement(**measurement))
        batch_one_circ_insert(measurements, chunk_size)
        print(f"Inserted {len(measurements)} one-hop measurements at {datetime.datetime.now()}")
    return True


async def setup(reactor, instance):
    [tor, config, state, socks] = await launch_tor(reactor, instance)
    assert (config.CircuitBuildTimeout == 10)
    assert (config.SocksTimeout == 10)
    assert (config.CircuitStreamTimeout == 10)
    routers = state.all_routers
    relays = list(routers)
    shuffle(relays)
    config = {"reactor": reactor, "tor": tor, "state": state, "relays": relays, "socks": socks}
    metadata = {
        "gcp_instance": get_gcp_metadata("name").text,
        "gcp_zone": get_gcp_metadata("zone").text.split("/")[-1],
        "measurer_id": uuid.uuid1(),
        "tor_pid": state.tor_pid,
        "tor_version": tor.version,
        "tor_instance": instance}
    return config, metadata


async def _main(reactor, arguments):
    print(f"Beginning Measurements at {datetime.datetime.now()}")
    db = getDatabase()
    print(arguments.database)
    db_args = db_url_parse(arguments.database)
    print(db_args)
    db.init(**db_args)
    db.connect()
    db.create_tables([TwoHopMeasurement, OneCircuitMeasurement])
    c, m = await setup(reactor, arguments.instance)
    print(
        f"Running as {m['measurer_id']} on {m['gcp_instance']} in {m['gcp_zone']} with tor instance '{m['tor_instance']}' with pid {m['tor_pid']}  v{m['tor_version']}")
    if arguments.mode == "one-hop":
        await test_one_circuit(c, m, c['relays'])
    elif arguments.mode == "exits":
        guard1 = c['state'].routers_by_hash["$6C251FA7F45E9DEDF5F69BA3D167F6BA736F49CD"]
        exits = list(filter(lambda router: "exit" in router.flags, c['relays']))
        await test_two_hops(c, m, [guard1], exits)
    elif arguments.mode == "guards":
        exit_node = c['state'].routers_by_hash["$606ECF8CA6F9A0C84165908C285F8193039A259D"]
        non_exits = list(filter(lambda router: "exit" not in router.flags, c['relays']))
        await test_two_hops(c, m, non_exits, [exit_node])
    db.close()


def main(arguments):
    return react(
        lambda reactor: ensureDeferred(
            _main(reactor, arguments)
        )
    )
