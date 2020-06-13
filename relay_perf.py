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

from Measurement import OneCircuitMeasurement, TwoHopMeasurement, batch_one_circ_insert, batch_two_hop_insert, \
    getDatabase


async def launch_tor(reactor, instance, uID):
    control_ep = UNIXClientEndpoint(reactor, f"/run/tor-instances/{instance}/control")
    tor = await txtorcon.connect(reactor, control_ep)
    config = await tor.get_config()
    state = await tor.create_state()
    socks = UNIXClientEndpoint(reactor, f"/run/tor-instances/{instance}/socks")
    return [tor, config, state, socks]


async def build_one_hop_circuit(reactor, state, target):
    circuit = None
    success = True
    error = ""
    t_start = datetime.datetime.now()
    try:
        circuitDef = state.build_circuit(routers=[target], using_guards=False)
        # circuitDef.addTimeout(10, reactor)
        circuit = await circuitDef
    except Exception as err:
        print(f"Err path exercised {err}")
        circuitDef.cancel()
        error = str(err)
        success = False
    if success:
        try:
            d = circuit.when_built()
            # d.addTimeout(10, reactor)
            await d
        except Exception as err:
            print(f"Err path exercised {err}")
            circuitDef.cancel()
            d.cancel()
            error = str(err)
            success = False
    t_stop = datetime.datetime.now()
    return circuit, {"success": success,
                     "t_start": t_start,
                     "t_stop": t_stop,
                     "error": error,
                     "target": target.id_hex}


async def build_two_hop_circuit(reactor, state, guard, exit_node):
    circuit = {}
    success = None
    error = ""
    t_start = datetime.datetime.now()
    try:
        circuitDef = state.build_circuit(routers=[guard, exit_node], using_guards=False)
        # circuitDef.addTimeout(20, reactor)
        circuit = await circuitDef
        d = circuit.when_built()
        # d.addTimeout(20, reactor)
        await d
        success = True
    except Exception as err:
        error = str(err)
        success = False
    t_stop = datetime.datetime.now()
    return circuit, {"success": success,
                     "t_start": t_start,
                     "t_stop": t_stop,
                     "error": error}


async def request_over_circuit(reactor, socks, circuit):
    success = None
    error = ""
    t_start = datetime.datetime.now()
    url = b"http://example.com"
    try:
        agent = circuit.web_agent(reactor, socks)
        resp = await agent.request(b'HEAD', url)
        success = True
    except Exception as err:
        error = str(err)
        success = False
    t_stop = datetime.datetime.now()
    return {"success": success,
            "t_start": t_start,
            "t_stop": t_stop,
            "error": error,
            "url": url}


def gracefulClose(circuit):
    if circuit is None:
        return
    if circuit.is_built:
        try:
            circuit.close()
        except Exception as err:
            return


async def time_two_hop(reactor, state, socks, guard, exit_node):
    timestamp = datetime.datetime.now()
    circuit, circuit_results = await build_two_hop_circuit(reactor, state, guard, exit_node)
    if circuit_results["success"]:
        request_results = await request_over_circuit(reactor, socks, circuit)
    else:
        request_results = {"success": False,
                           "t_start": None,
                           "t_stop": None,
                           "error": "NO_CIRCUIT",
                           "url": None}
    measurement = {"t_measure": timestamp,
                   "guard": guard.id_hex,
                   "exit": exit_node.id_hex,
                   "circuit": circuit_results,
                   "request": request_results}
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


def resultToTwoHopMeasurement(result, metadata):
    return TwoHopMeasurement(timestamp=result['t_measure'],
                             guard=result['guard'],
                             exit=result['exit'],
                             url=result['request']['url'],
                             circuit_success=result['circuit']['success'],
                             circuit_time=getDeltaMilli(result['circuit']['t_start'], result['circuit']['t_stop']),
                             circuit_error=result['circuit']['error'],
                             request_success=result['request']['success'],
                             request_time=getDeltaMilli(result['request']['t_start'],
                                                        result['request']['t_stop']),
                             request_error=result['request']['error'],
                             **metadata,
                             )


def resultToOneCircMeasurement(result, metadata):
    return TwoHopMeasurement(timestamp=result['t_measure'],
                             target=result['target'],
                             circuit_success=result['success'],
                             circuit_time=getDeltaMilli(result['t_start'], result['t_stop']),
                             circuit_error=result['error'],
                             **metadata
                             )


async def test_two_hops(config, metadata, sources, exits):
    nr = len(sources)
    ne = len(exits)
    measurements = list()
    for relay, exit_node in tqdm(product(sources, exits), total=nr * ne, leave=False):
        result = await time_two_hop(config, relay, exit_node)
        measurements.append(resultToTwoHopMeasurement(result, metadata))
    batch_two_hop_insert(measurements, 200)
    print(f"Inserted {len(measurements)} two-hop measurements at {datetime.datetime.now()}")
    return True


async def test_one_circuit(config, metadata, targets, chunk_size=100):
    for chunk in chunked(targets, chunk_size):
        measurements = list()
        for t in tqdm(chunk, total=chunk_size, leave=False):
            timestamp = datetime.datetime.now()
            try:
                c, result = await build_one_hop_circuit(config['reactor'], config['state'], t)
                gracefulClose(c)
            except Exception as err:
                print(f"Top Level Error: {err}")
                continue
            result['t_measure'] = timestamp
            measurements.append(resultToOneCircMeasurement(result, metadata))
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
        "gcp_inst": get_gcp_metadata("name").text,
        "gcp_zone": get_gcp_metadata("zone").text.split("/")[-1],
        "uuid": uuid.uuid1(),
        "tor_pid": state.tor_pid,
        "tor_version": tor.version,
        "tor_instance": instance}
    return config,metadata


async def _main(reactor, arguments):
    print(f"Beginning Measurements at {datetime.datetime.now()}")
    db = getDatabase()
    db.init(arguments.database)
    db.connect()
    db.create_tables([TwoHopMeasurement, OneCircuitMeasurement])
    c, m = await setup(reactor, arguments.instance)
    print(
        f"Running as {m['uuid']} on {m['gcp_inst']} in {m['gcp_zone']} with Tor instance {m['tor_instance']} pid {m['tor_pid']}  v{m['tor_version']}")
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
