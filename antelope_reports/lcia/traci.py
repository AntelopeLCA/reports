"""
Support operations for TRACI LCIA Methods
"""
from antelope import EntityNotFound


def traci_2_replicate_nox_no2(q):
    """
    For any LCIA method, replicate factors of 'nitrogen oxides' flowable to 'nitrogen dioxide' flowable
    Applicable to USEEIO 1.1 implementation of TRACI 2.1.
    :param q:
    :return:
    """
    for cf in q.factors(flowable='nitrogen oxides'):
        q.characterize(flowable='nitrogen dioxide', ref_quantity=cf.ref_quantity, context=cf.context, value=cf.value)


def traci_2_combined_eutrophication(traci, fg, external_ref='Eutrophication'):
    """
    Construct a combined eutrophication indicator that is the union of the TRACI 2.1 Eutrophication Air and
    Eutrophication Water methods.
    :param traci: Catalog query containing the TRACI 2.1 implementation
    :param fg: Foreground to contain the new combined eutrophication method
    :param external_ref: ('Eutrophication') what external reference to assign to the newly created quantity
    :return:
    """
    old_euts = [traci.get(k) for k in ('Eutrophication Air', 'Eutrophication Water')]
    try:
        return fg.get(external_ref)
    except EntityNotFound:
        pass

    new_eut = fg.new_quantity('Eutrophication Air + Water', ref_unit='kg N eq', external_ref=external_ref,
                              Method='TRACI 2.1 - Reference',
                              Category='Eutrophication', ShortName='Eutrophication', Indicator='kg N eq',
                              uuid='69726949-4add-4605-8f40-61e56f2b412c',
                              Comment="Union of TRACI 2.1 'Eutrophication Air' and 'Eutrophication Water'")
    for eu in old_euts:
        for cf in eu.factors():
            for loc in cf.locations:
                new_eut.characterize(flowable=cf.flowable, ref_quantity=cf.ref_quantity, context=cf.context,
                                     value=cf[loc], location=loc, origin=cf.origin)
    return new_eut
