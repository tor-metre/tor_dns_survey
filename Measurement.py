from peewee import *

db = SqliteDatabase(None)

def getDatabase():
    return db

def batch_two_hop_insert(measurements, batch):
    with db.atomic():
        TwoHopMeasurement.bulk_create(measurements, batch)

def batch_one_circ_insert(measurements, batch):
    with db.atomic():
        OneCircuitMeasurement.bulk_create(measurements, batch)

class TwoHopMeasurement(Model):
    process = UUIDField()
    tor_version = TextField()
    gcp_instance = TextField()
    gcp_zone = TextField()

    timestamp = DateTimeField()
    guard = TextField()
    exit = TextField()
    url = TextField(null=True)

    circuit_success = BooleanField()
    circuit_time = IntegerField()
    circuit_error = CharField()

    request_success = BooleanField()
    request_time = IntegerField()
    request_error = CharField()
    class Meta:
        database = db

class OneCircuitMeasurement(Model):
    process = UUIDField()
    tor_version = TextField()
    gcp_instance = TextField()
    gcp_zone = TextField()

    timestamp = DateTimeField()
    target = TextField()

    circuit_success = BooleanField()
    circuit_time = IntegerField()
    circuit_error = CharField()

    class Meta:
        database = db
