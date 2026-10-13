FROM python:3.12-slim
RUN pip install --no-cache-dir --no-deps evalplus==0.3.1 && \
    pip install --no-cache-dir numpy==2.2.6 psutil==7.0.0
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
COPY runner.py /opt/runner.py
USER 65534:65534
ENTRYPOINT ["python", "-I", "/opt/runner.py"]
