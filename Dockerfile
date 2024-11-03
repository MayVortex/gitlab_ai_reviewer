FROM python

WORKDIR /app

COPY code/. .

RUN pip install -e .

CMD ["/bin/bash"]
