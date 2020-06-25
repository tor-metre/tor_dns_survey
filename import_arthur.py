from json import loads
from glob import glob
from tqdm import tqdm
from playhouse.db_url import parse as db_url_parse
from Measurement import getDatabase, ArthurMeasurement


def process(contents):
    results = []
    for target in contents.keys():
        if target == "_relays":
            continue
        for e in contents[target].keys():
            for (state, time, latency) in contents[target][exit]:
                if state == "SUCCEEDED":
                    state = True
                else:
                    state = False
                latency = int(latency * 1000)
                results.append(ArthurMeasurement(timestamp=time, url=target, exit=e, success=state, latency=latency))
    with db.atomic():
        ArthurMeasurement.bulk_create(results, 2000)


db = getDatabase()
db_args = db_url_parse("postgresql://observatory:tess12345@127.0.0.1:5432/testing")
db.init(**db_args)
db.connect()
db.create_tables([ArthurMeasurement])

for p in tqdm(glob("/media/dennis/Dennis SSD/tor-consensus-info/exit_survey/**/*.json", recursive=True)):
    f = open(p, 'r')
    c = f.read()
    j = loads(c)
    process(j)
