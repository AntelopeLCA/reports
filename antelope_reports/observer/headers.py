"""
Antelope Observer
worksheets and column headings

An observer xlsx-like should have the following sheets:

<archive contents>
flows, quantities, flowproperties

<quick-and-easy>
spanners - list of annotated models
a sheet for each model named
note: all columns that appear in a model listing will be applied. add fields with abandon.

taps - flows to be tapped, and where they should be tapped to
observations - exchange values and anchors to be applied to the model

<model maker>
production - complete fragment specification

The list of headers for each sheet are provided below in a canonical order and capitalization. 
Order is not binding (row dictionary index required) but case should be observed.  
"""

QUANTITIES_HEADER = ('external_ref', 'referenceUnit', 'Name', 'Comment', 'Synonyms')
FLOWS_HEADER = ('external_ref', 'referenceQuantity', 'Name', 'Comment', 'Compartment')
FLOWPROPERTIES_HEADER = ('flow', 'ref_quantity', 'ref_unit', 'quantity', 'unit', 'value', 'source', 'note')

SPANNERS_META = ('spanner', 'name', 'description', 'author', 'source', 'version')

SPANNER_HEADER = ('flow', 'amount', 'direction', 'unit', 'type', 'Name', 'Comment', 'stage_name', 'grouping', 'note')

PRODUCTION_HEADER = ('prod_flow', 'ref_direction', 'ref_value', 'ref_unit',
                     'direction', 'balance_yn', 'child_flow', 'units', 'amount', 'amount_hi', 'amount_lo',
                     'stage_name',
                     'target_origin', 'target_flow', 'target_name', 'target_ref', 'locale',
                     'add_taps', 'note', 'Comment', 'compartment')

OBSERVATIONS_HEADER = ('activity', 'child_flow', 'scenario', 'parameter', 'units',
                       'anchor_origin', 'anchor', 'anchor_flow', 'descend', 'comment')
