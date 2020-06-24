from peewee import *

db = PostgresqlDatabase(None)

def getDatabase():
    return db

def batch_two_hop_insert(measurements, batch):
    with db.atomic():
        TwoHopMeasurement.bulk_create(measurements, batch)

def batch_one_circ_insert(measurements, batch):
    with db.atomic():
        OneCircuitMeasurement.bulk_create(measurements, batch)

class ArthurMeasurement(Model):
    timestamp = DateTimeField(unique=True)
    url = TextField()
    exit = TextField()
    success = BooleanField()
    latency = IntegerField()
    class Meta:
        database = db

class TwoHopMeasurement(Model):
    measurer_id = UUIDField()
    tor_pid = IntegerField()
    tor_version = TextField()
    tor_instance = TextField()
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
    measurer_id = UUIDField()
    tor_pid = IntegerField()
    tor_version = TextField()
    tor_instance = TextField()
    gcp_instance = TextField()
    gcp_zone = TextField()

    timestamp = DateTimeField()
    target = TextField()

    circuit_success = BooleanField()
    circuit_time = IntegerField()
    circuit_error = CharField()

    class Meta:
        database = db
