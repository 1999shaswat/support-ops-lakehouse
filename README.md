# Support Ticket Intelligence
Support tickets based BI Dashboard that helps make business decisions based on data

### Dataset Limitations
- product_segment being randomly assigned per product (unrelated to which customers actually buy it)
- two synthetic source systems, split arbitrarily, to simulate ingesting from heterogeneous systems
- flat 35% skew toward Technical Support regardless of product

### Transformations:
- Denormalize dim_company + dim_customer to carry company_name/segment/region in silver/gold (Kimball)