from pyspark.sql import functions as F
from common import get_sedona
from config import p

source = p("staging", "facilities", "fac_maharashtra_state.geojsonl")
destination = p("out", "facilities")

sedona = get_sedona("restore_facilities")

try:
    fac = sedona.read.text(source)

    fac = fac.select(
        F.get_json_object("value", "$.properties.amenity").alias("amenity"),
        F.get_json_object("value", "$.properties.healthcare").alias("healthcare"),
        F.get_json_object("value", "$.geometry").alias("gj"),
    ).where("gj IS NOT NULL")

    fac = (
        fac.withColumn(
            "facility_type",
            F.when(
                (F.col("amenity") == "hospital")
                | (F.col("healthcare") == "hospital"),
                "hospital",
            )
            .when(F.col("amenity") == "school", "school")
            .when(F.col("amenity") == "drinking_water", "drinking_water"),
        )
        .where("facility_type IS NOT NULL")
    )

    fac.createOrReplaceTempView("facility_features")

    result = sedona.sql("""
        SELECT
            facility_type,
            ST_X(ST_Centroid(ST_GeomFromGeoJSON(gj))) AS lon,
            ST_Y(ST_Centroid(ST_GeomFromGeoJSON(gj))) AS lat
        FROM facility_features
        WHERE ST_GeomFromGeoJSON(gj) IS NOT NULL
    """)

    print("Facility counts:")
    result.groupBy("facility_type").count().orderBy("facility_type").show()

    result.write.mode("overwrite").parquet(destination)
    print(f"Facility Parquet restored at: {destination}")

finally:
    sedona.stop()
