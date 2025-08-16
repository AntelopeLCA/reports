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
from pydantic import BaseModel
import re


valid_ref = re.compile('[A-Za-z0-9-_.]+')


class SpannerMeta(BaseModel):
    """
    metadata for fragment models
    """
    '''
    apparently there's no way to sync this pydantic model with SPANNERS_META
    '''
    external_ref: str
    name: str
    description: str
    author: str
    source: str
    version: str

    @classmethod
    def from_form(cls, external_ref, name=None, description='SpannerMeta', author='observer', source='observed',
                  version='0.1'):
        assert bool(valid_ref.match(external_ref)), 'Invalid external reference %s' % external_ref

        if name is None:
            name = external_ref

        return cls(external_ref=external_ref, name=name, description=str(description), author=str(author),
                   source=str(source), version=str(version))


QUANTITIES_HEADER = ('external_ref', 'referenceUnit', 'Name', 'Comment', 'Synonyms')
FLOWS_HEADER = ('external_ref', 'referenceQuantity', 'Name', 'Comment', 'Compartment')
FLOWPROPERTIES_HEADER = ('flow', 'ref_quantity', 'ref_unit', 'quantity', 'unit', 'value', 'source', 'note')

SPANNERS_META = ('external_ref', 'name', 'description', 'author', 'source', 'version')

SPANNER_HEADER = ('flow', 'direction', 'Name', 'amount', 'units', 'amount_hi', 'amount_lo', 'context', 'descend',
                  'Comment',
                  'stage_name', 'grouping', 'note')

PRODUCTION_HEADER = ('prod_flow', 'ref_direction', 'ref_value', 'ref_unit',
                     'direction', 'balance_yn', 'child_flow', 'units', 'amount', 'amount_hi', 'amount_lo',
                     'descend', 'stage_name',
                     'target_origin', 'target_flow', 'target_name', 'target_ref', 'locale',
                     'add_taps', 'note', 'Name', 'Comment', 'compartment')

TAPS_HEADER = ('tap_recipe', 'flow_origin', 'flow_name_or_ref', 'direction', 'target_origin', 'target_ref', 
               'adjust_value', 'scale_value', 'value_units')

OBSERVATIONS_HEADER = ('activity', 'child_flow', 'scenario', 'parameter', 'units',
                       'anchor_origin', 'anchor', 'anchor_flow', 'descend', 'comment')


HEADERS = {
    'quantities': QUANTITIES_HEADER,
    'flows': FLOWS_HEADER,
    'flowproperties': FLOWPROPERTIES_HEADER,
    'spanners': SPANNERS_META,
    'spanner': SPANNER_HEADER,
    'production': PRODUCTION_HEADER,
    'taps': TAPS_HEADER,
    'observations': OBSERVATIONS_HEADER
}


WIDTHS = {
    'production': {'prod_flow': 220,
                   'child_flow': 170,
                   'direction': 69,
                   'units': 69,
                   'descend': 65,
                   'amount': 75,
                   'amount_hi': 75,
                   'amount_lo': 75
                   },
    'flows': {'external_ref': 220,
              'referenceQuantity': 140,
              'Name': 300},
    'quantities': {'external_ref': 220,
                   'referenceUnit': 140,
                   'Name': 300},
    'flowproperties': {'flow': 220},
    'observations': {'activity': 220,
                     'child_flow': 220,
                     'units': 69},
    'taps': {'tap_recipe': 200},
    'spanners': {'external_ref': 150,
                 'name': 220,
                 'author': 160},
    'spanner': {'flow': 220,
                'Name': 260,
                'units': 69,
                'amount': 75,
                'amount_hi': 65,
                'amount_lo': 65,
                'context': 60,
                'descend': 60
                }
    }


_flows = _dark_magenta = [k/256 for k in (0xcb, 0, 0xcb)]
_model = _dark_green = [k/256 for k in (0x21, 0xa2, 0x60)]
_study = _cornflower_blue = [k/256 for k in (0x64, 0x95, 0xed)]


TAB_COLORS = {
    'quantities': _flows,
    'flows': _flows,
    'flowproperties': _flows,
    'spanners': _model,
    'spanner': _model,
    'production': _study,
    'taps': _study,
    'observations': _study
}
