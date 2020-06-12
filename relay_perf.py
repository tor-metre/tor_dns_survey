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

from Measurement import OneCircuitMeasurement,TwoHopMeasurement, batch_one_circ_insert, batch_two_hop_insert, getDatabase

async def launch_tor(reactor, instance,uID):
    control_ep = UNIXClientEndpoint(reactor, f"/run/tor-instances/{instance}/control")
    tor = await txtorcon.connect(reactor, control_ep)
    config = await tor.get_config()
    state = await tor.create_state()
    socks = UNIXClientEndpoint(reactor,f"/run/tor-instances/{instance}/socks")
    return [tor, config, state, socks]

async def build_one_hop_circuit(reactor, state, target):
    circuit = None
    success = True
    error = ""
    t_start = datetime.datetime.now()
    try:
        circuitDef = state.build_circuit(routers=[target], using_guards=False)
        #circuitDef.addTimeout(10, reactor)
        circuit = await circuitDef
    except Exception as err:
        print(f"Err path exercised {err}")
        circuitDef.cancel()
        error = str(err)
        success = False
    if success:
        try:
            d = circuit.when_built()
            #d.addTimeout(10, reactor)
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
        #circuitDef.addTimeout(20, reactor)
        circuit = await circuitDef
        d = circuit.when_built()
        #d.addTimeout(20, reactor)
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


def resultToTwoHopMeasurement(result, tv, uID, gcpI, gcpZ):
    return TwoHopMeasurement(timestamp=result['t_measure'],
                             tor_version=tv,
                             process=uID,
                             gcp_instance=gcpI,
                             gcp_zone=gcpZ,
                             guard=result['guard'],
                             exit=result['exit'],
                             url=result['request']['url'],
                             circuit_success=result['circuit']['success'],
                             circuit_time=getDeltaMilli(result['circuit']['t_start'], result['circuit']['t_stop']),
                             circuit_error=result['circuit']['error'],
                             request_success=result['request']['success'],
                             request_time=getDeltaMilli(result['request']['t_start'],
                                                        result['request']['t_stop']),
                             request_error=result['request']['error']
                             )


def resultToOneCircMeasurement(result, tv, uID, gcpI, gcpZ):
    return TwoHopMeasurement(timestamp=result['t_measure'],
                             tor_version=tv,
                             process=uID,
                             gcp_instance=gcpI,
                             gcp_zone=gcpZ,
                             target=result['target'],
                             circuit_success=result['success'],
                             circuit_time=getDeltaMilli(result['t_start'], result['t_stop']),
                             circuit_error=result['error'],
                             )


async def test_two_hops(reactor, state, socks, relays, exits, repeats, tv, gcpI, gcpZ, uID):
    nr = len(relays)
    ne = len(exits)
    n = nr * ne * repeats
    for i in range(repeats):
        measurements = list()
        for relay, exit_node in tqdm(product(relays, exits), total=nr * ne, leave=False):
            result = await time_two_hop(reactor, state, socks, relay, exit_node)
            measurements.append(resultToTwoHopMeasurement(result, tv, gcpI, gcpZ, uID))
        batch_two_hop_insert(measurements, 200)
        print(f"Inserted {len(measurements)} records at {datetime.datetime.now()}")
    return n


async def test_one_circuit(reactor, state, targets, repeats, tv, gcpI, gcpZ, uID):
    nr = len(targets)
    n = nr * repeats
    chunkSize= 100
    for i in range(repeats):
        for chunk in chunked(targets,chunkSize):
            measurements = list()
            for t in tqdm(chunk,total=chunkSize,leave=False):
                timestamp = datetime.datetime.now()
                try:
                    c,result = await build_one_hop_circuit(reactor, state, t)
                    gracefulClose(c)
                except Exception as err:
                    print(f"Top Level Error: {err}")
                result['t_measure'] = timestamp
                measurements.append(resultToOneCircMeasurement(result, tv, gcpI, gcpZ, uID))
            batch_one_circ_insert(measurements, chunkSize)
            print(f"Inserted {len(measurements)} records at {datetime.datetime.now()}")
    return n

async def setup(reactor,instance):
    uID = uuid.uuid1()
    [tor, config, state, socks] = await launch_tor(reactor, instance, uID)
    gcpI = get_gcp_metadata("name").text
    gcpZ = get_gcp_metadata("zone").text.split("/")[-1]
    print(f"Running as {uID} on {gcpI} in {gcpZ} with Tor {tor.version}")
    config.CircuitBuildTimeout = 10
    config.SocksTimeout = 10
    config.CircuitStreamTimeout = 10
    #config.save() #TODO Fix this
    routers = state.all_routers
    relays = list(routers)
    shuffle(relays)
    return tor,state,relays,socks,gcpI,gcpZ,uID

async def _main(reactor,arguments):
    print(f"Beginning Measurements at {datetime.datetime.now()}")
    db = getDatabase()
    db.init(arguments.database)
    db.connect()
    db.create_tables([TwoHopMeasurement,OneCircuitMeasurement])
    #TODO store tor.pid and instance name
    tor,state,relays,socks,gcpI,gcpZ,uID = await setup(reactor,arguments.instance)

    if arguments.mode == "one-hop":
        await test_one_circuit(reactor, state, relays, 1, tor.version, gcpI, gcpZ, uID)
    elif arguments.mode == "exits":
        guard1 = state.routers_by_hash["$6C251FA7F45E9DEDF5F69BA3D167F6BA736F49CD"]
        exits = list(filter(lambda router: "exit" in router.flags, relays))
        await test_two_hops(reactor, state, socks, [guard1], exits, 1, tor.version, gcpI, gcpZ, uID)
    elif arguments.mode == "guards":
        exit_node = state.routers_by_hash["$606ECF8CA6F9A0C84165908C285F8193039A259D"]
        relays = list(filter(lambda router: "exit" not in router.flags, relays))
        await test_two_hops(reactor, state, socks, relays, [exit_node], 1, tor.version, gcpI, gcpZ,
                                            uID)
    db.close()

def main(arguments):
    return react(
        lambda reactor: ensureDeferred(
            _main(reactor, arguments)
        )
    )