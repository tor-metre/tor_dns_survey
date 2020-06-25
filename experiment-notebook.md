# Experiment Notebook

## One Hop Measurements
  
Retrofitted Arthur's Exit Testing script to measure one-hop latency and put the results in Postgres. 
Set four instances running a on Google Cloud instance in Amsterdam. 
It is gathering quite granular data on latency of different servers.
Should be sampling *every* relay at ~15 minute intervals. 

Expect this data will be useful in the future. Much more detailed than Tor Metrics, although doesn't actually do round trips. 

## Historical Correlation Analysis 

Plan:
	* Ingest extra-info descriptors into postgres
	* Ingest Arthur's historical exit relay data. 
	* Attempt to use Little's Law / expected queue latency. In principle - hope to see long term variations in mean latency depending on capacity used? 
	* Spearman's correlation test? 

```
CREATE VIEW wrote_vs_latency AS SELECT wrotebyteshistory.fingerprint, wrotebyteshistory.startpoint, wrotebyteshistory.endpoint, wrotebyteshistory.bytes_wrote, AVG(arthurmeasurement.latency) FROM wrotebyteshistory LEFT JOIN arthurmeasurement ON wrotebyteshistory.fingerprint = arthurmeasurement.exit AND arthurmeasurement.timestamp BETWEEN wrotebyteshistory.startpoint AND wrotebyteshistory.endpoint GROUP BY wrotebyteshistory.fingerprint, wrotebyteshistory.startpoint, wrotebyteshistory.endpoint, wrotebyteshistory.bytes_wrote HAVING count(arthurmeasurement.latency) > 5;
```

Don't forget index on wrotebyteshistory!

