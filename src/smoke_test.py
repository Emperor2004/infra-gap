"""Checks that Sedona works, work runs on both workers, and the shared /data folder is writable."""
import socket

from common import get_sedona
from config import p

sedona = get_sedona("smoke-test")

print(sedona.sql("SELECT ST_Point(73.85, 18.52) AS p").first())
print(sedona.sql("SELECT ST_H3CellIDs(ST_Point(73.85, 18.52), 8, false) AS h").first())
print(sedona.sql("SELECT ST_DistanceSphere(ST_Point(73.85, 18.52), ST_Point(73.86, 18.53)) AS d").first())
print(sedona.sql("SELECT ST_H3ToGeom(ST_H3CellIDs(ST_Point(73.85, 18.52), 8, false)) AS g").first())

hosts = (sedona.sparkContext.parallelize(range(400), 10)
         .map(lambda _: socket.gethostname()).distinct().collect())
print("executor hosts:", sorted(hosts))

path = p("staging", "smoke")
sedona.range(1000).write.mode("overwrite").parquet(path)
print("rows read back:", sedona.read.parquet(path).count())