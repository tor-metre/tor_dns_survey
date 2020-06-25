from peewee import *
from tqdm import tqdm
from playhouse.db_url import parse as db_url_parse
from stem.descriptor.reader import DescriptorReader
from datetime import timedelta

db = PostgresqlDatabase(None)


class WroteBytesHistory(Model):
    fingerprint = TextField()
    startpoint = DateTimeField()
    endpoint = DateTimeField()
    bytes_wrote = BigIntegerField()

    class Meta:
        database = db


class ReadBytesHistory(Model):
    fingerprint = TextField()
    startpoint = DateTimeField()
    endpoint = DateTimeField()
    bytes_read = BigIntegerField()

    class Meta:
        database = db


print("Setting up Database...")
db_args = db_url_parse("postgresql://observatory:tess12345@127.0.0.1:5432/testing")
db.init(**db_args)
db.connect()
db.drop_tables([WroteBytesHistory, ReadBytesHistory])
db.create_tables([WroteBytesHistory, ReadBytesHistory])

print("Loading Descriptor Reader...")
reader = DescriptorReader(['/media/dennis/Dennis SSD/tor-consensus-info/extra_info/'])


def parse_intervals(interval_duration, final_endpoint, intervals):
    num_intervals = len(intervals)
    results = list()
    for i in range(num_intervals):
        t_endpoint = final_endpoint - ((num_intervals - i) * interval_duration)
        t_startpoint = t_endpoint - interval_duration
        value = intervals[i]
        results.append((t_startpoint, t_endpoint, value))
    return results


print("Beginning Processing...")
wrote_records = list()
read_records = list()
with reader:
    for d in tqdm(reader):
        t_fingerprint = d.fingerprint
        if t_fingerprint is None:
            print(f"Missing Fingerprint for {d}")
            continue
        if d.write_history_values is not None:
            interval_duration = timedelta(seconds=d.write_history_interval)
            final_endpoint = d.write_history_end
            results = parse_intervals(interval_duration, final_endpoint, d.write_history_values)
            for (t_start, t_end, t_wrote) in results:
                wrote_records.append(WroteBytesHistory(fingerprint=t_fingerprint,
                                                       startpoint=t_start,
                                                       endpoint=t_end,
                                                       bytes_wrote=t_wrote))
        if d.read_history_values is not None:
            interval_duration = timedelta(seconds=d.read_history_interval)
            final_endpoint = d.read_history_end
            results = parse_intervals(interval_duration, final_endpoint, d.read_history_values)
            for (t_start, t_end, t_read) in results:
                read_records.append(ReadBytesHistory(fingerprint=t_fingerprint,
                                                     startpoint=t_start,
                                                     endpoint=t_end,
                                                     bytes_read=t_read))
        if len(wrote_records) > 10000:
            with db.atomic():
                WroteBytesHistory.bulk_create(wrote_records,2000)
            wrote_records = list()
        if len(read_records) > 10000:
            with db.atomic():
                ReadBytesHistory.bulk_create(read_records,2000)
            read_records = list()
