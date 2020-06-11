from peewee import *

db = SqliteDatabase('measurements.db')

def getDatabase():
    return db

def batch_insert(measurements,batch):
    with db.atomic():
        Measurement.bulk_create(measurements, batch)

class Measurement(Model):
    t_measure = DateTimeField()
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
