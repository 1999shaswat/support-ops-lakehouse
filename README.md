# Support Ticket Intelligence
Support tickets based BI Dashboard that helps make business decisions based on data

### Dataset Limitations
- product_segment being randomly assigned per product (unrelated to which customers actually buy it)
- two synthetic source systems, split arbitrarily, to simulate ingesting from heterogeneous systems
- flat 35% skew toward Technical Support regardless of product

### Transformations:
- Denormalize dim_company + dim_customer to carry company_name/segment/region in silver/gold (Kimball)

### Bugs
- Team isn’t on the created records. It exists only via agent_id → agents. Null or blank agents therefore have no team.
  - one issue i can see that might happen is mismatch between agent's team and product category. is that an issue? if yes, how to fix?
  
- Transfer teams are random, so from_team isn’t tied to the ticket’s assigned agent’s team.
  - issue i can see is mismatch between ticket-created/resolved:agent and transfer:from_team or to_team. how to fix it?
  
- No region on tickets. Region only exists on companies and agents.
  - is this an issue? i don't think so.
  
- Partition date ≠ event timestamp. Resolved files are partitioned by created day plus a random delay (mean about 3 days), independent of the actual resolved_at. Created timestamps also carry the time of day of when you ran the script, so they can spill past midnight relative to their dt= folder.
  - is that an issue? how to fix it?
  
- Late events: resolved partitions can land after the end of the backfill window.
  - is that an issue? how to fix it?
  
- Event ordering: a transfer can occur after a ticket’s resolved_at, since the two are generated independently.
  - how to fix it?
  
- Live mode only emits created and transfer events, never resolved ones.
  - how to fix it?
