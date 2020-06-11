import asyncio
import datetime
import json
import os
import time
import txtorcon
import urllib.request

from twisted.internet import asyncioreactor
from twisted.internet.defer import ensureDeferred
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.task import react

from Measurement import Measurement, batch_insert, getDatabase


async def launch_tor(reactor):
    control_ep = TCP4ClientEndpoint(reactor, "localhost", 9051)
    tor = await txtorcon.connect(reactor, control_ep, password_function=lambda: "bilboBaggins789")
    # tor = await txtorcon.launch(reactor, progress_updates=print, data_directory="./tor_data")
    config = await tor.get_config()
    state = await tor.create_state()
    socks = await config.create_socks_endpoint(reactor, "9050")
    print("Connected to tor {}".format(tor.version))
    return [tor, config, state, socks]


async def build_two_hop_circuit(reactor, state, guard, exit_node):
    circuit = {}
    success = None
    error = ""
    t_start = datetime.datetime.now()
    try:
        circuitDef = state.build_circuit(routers=[guard, exit_node], using_guards=False)
        circuitDef.addTimeout(60, reactor)
        circuit = await circuitDef
        d = circuit.when_built()
        d.addTimeout(60, reactor)
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


async def request_over_circuit(reactor, socks, circuit, bareIP):
    success = None
    error = ""
    t_start = datetime.datetime.now()
    url = b"http://93.184.216.34" if bareIP else b"http://example.com"
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


async def time_two_hop(reactor, state, socks, guard, exit_node, bareIP):
    timestamp = datetime.datetime.now()
    circuit, circuit_results = await build_two_hop_circuit(reactor, state, guard, exit_node)
    if circuit_results["success"]:
        request_results = await request_over_circuit(reactor, socks, circuit, bareIP)
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
    return measurement


async def test_relays(reactor, state, socks, relays, exits, repeats, bareIP):
    nr = len(relays)
    ne = len(exits)
    n = nr * ne * repeats
    for i in range(repeats):
        j = 0
        measurements = list()
        for relay in relays:
            for exit_node in exits:
                j = j + 1
                result = await time_two_hop(reactor, state, socks, relay, exit_node, bareIP)
                measurements.append(Measurement(t_measure=result['t_measure'],
                                                guard=result['guard'],
                                                exit=result['exit'],
                                                url=result['request']['url'],
                                                circuit_success=result['circuit']['success'],
                                                circuit_t_start=result['circuit']['t_start'],
                                                circuit_t_stop=result['circuit']['t_stop'],
                                                circuit_error=result['circuit']['error'],
                                                request_success=result['request']['success'],
                                                request_t_start=result['request']['t_start'],
                                                request_t_stop=result['request']['t_stop'],
                                                request_error=result['request']['error']
                                                # TODO Record more fields
                                                ))
        batch_insert(measurements, 200)
    return n


async def _main(reactor, fingerprint, bareIP):
    [tor, config, state, socks] = await launch_tor(reactor)
    config.CircuitBuildTimeout = 10
    config.SocksTimeout = 10
    config.CircuitStreamTimeout = 10
    config.save()
    if fingerprint == None:
        routers = state.all_routers
    else:
        routers = [state.routers_by_hash[fingerprint]]

    guard1 = state.routers_by_hash["$6C251FA7F45E9DEDF5F69BA3D167F6BA736F49CD"]
    exits = list(filter(lambda router: "exit" in router.flags, routers))
    exit_results = await test_relays(reactor, state, socks, [guard1], exits, 10, bareIP)
    print(exit_results)

    exit_node = state.routers_by_hash["$606ECF8CA6F9A0C84165908C285F8193039A259D"]
    relays = list(filter(lambda router: "exit" not in router.flags, routers))
    relay_results = await test_relays(reactor, state, socks, relays, [exit_node], 3, False)
    print(relay_results)


def main(fingerprint, bareIP):
    return react(
        lambda reactor: ensureDeferred(
            _main(reactor, fingerprint, bareIP)
        )
    )


if __name__ == '__main__':
    db = getDatabase()
    db.connect()
    db.create_tables([Measurement])
    main(None, False)
    db.close()
