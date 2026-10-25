FROM eclipse-temurin:11-jdk-jammy

ARG SPARK_VER=3.5.7
ARG SEDONA_VER=1.9.1
ARG GEOTOOLS_VER=1.9.1-33.5

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip curl ca-certificates procps git gdal-bin osmium-tool \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://archive.apache.org/dist/spark/spark-${SPARK_VER}/spark-${SPARK_VER}-bin-hadoop3.tgz \
      | tar xz -C /opt && mv /opt/spark-${SPARK_VER}-bin-hadoop3 /opt/spark

RUN curl -fsSL -o /opt/spark/jars/sedona-spark-shaded-3.5_2.12-${SEDONA_VER}.jar \
      https://repo1.maven.org/maven2/org/apache/sedona/sedona-spark-shaded-3.5_2.12/${SEDONA_VER}/sedona-spark-shaded-3.5_2.12-${SEDONA_VER}.jar \
 && curl -fsSL -o /opt/spark/jars/geotools-wrapper-${GEOTOOLS_VER}.jar \
      https://repo1.maven.org/maven2/org/datasyslab/geotools-wrapper/${GEOTOOLS_VER}/geotools-wrapper-${GEOTOOLS_VER}.jar

RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir pyspark==${SPARK_VER} apache-sedona==${SEDONA_VER} \
      shapely attrs pandas pyarrow geopandas pyogrio "h3>=4" mercantile rasterio requests tqdm scipy matplotlib

ENV SPARK_HOME=/opt/spark \
    PYSPARK_PYTHON=/opt/venv/bin/python \
    PATH=/opt/spark/bin:/opt/venv/bin:$PATH

COPY spark-defaults.conf /opt/spark/conf/spark-defaults.conf
WORKDIR /workspace