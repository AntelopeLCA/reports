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


def traci_2_combined_eutrophication(traci, fg, external_ref='Eutrophication', omit_n2=True):
    """
    Construct a combined eutrophication indicator that is the union of the TRACI 2.1 Eutrophication Air and
    Eutrophication Water methods.
    :param traci: Catalog query containing the TRACI 2.1 implementation
    :param fg: Foreground to contain the new combined eutrophication method
    :param external_ref: ('Eutrophication') what external reference to assign to the newly created quantity
    :param omit_n2: [True] skip the CF on gaseous nitrogen
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
            if str(cf.flowable).lower() == 'nitrogen' and cf.context.name in ('air', 'to air'):
                if omit_n2:
                    print('Omitting gaseous nitrogen to air eutrophication\n%s' % cf)
                    for loc in cf.locations:
                        new_eut.characterize(flowable=cf.flowable, ref_quantity=cf.ref_quantity, context=cf.context,
                                             value=0.0, location=loc, origin=cf.origin)
                    continue

            for loc in cf.locations:
                new_eut.characterize(flowable=cf.flowable, ref_quantity=cf.ref_quantity, context=cf.context,
                                     value=cf[loc], location=loc, origin=cf.origin)
    return new_eut


def traci_2_biogenic_co2(traci, fg, external_ref='gwp_bio_co2', indicator='kg CO2eq incl bio'):
    """
    Duplicate the GWP method, but force the duplicate to compute biogenic CO2: see
    antelope_core.implementations.quantity.do_lcia()
    antelope_core.implementations.quantity.CO2QuantityConversion
    antelope.flow.Flow.is_co2
    :param traci:
    :param fg:
    :param external_ref:
    :param indicator:
    :return:
    """
    try:
        return fg.get(external_ref)
    except EntityNotFound:
        pass

    old_gwp = traci.get('Global Warming Air')
    new_gwp = fg.new_quantity('Global Warming Air - with biogenic CO2', ref_unit=indicator,
                              external_ref=external_ref,
                              Method=old_gwp['Method'], Category='Global Warming Air - including biogenic CO2',
                              Indicator=indicator,
                              uuid='64583b7d-bdd0-4d44-ae53-494d5b192606',
                              Comment='TRACI GWP method with biogenic CO2 enforced',
                              quell_biogenic_co2=False)
    old_gwp['quell_biogenic_co2'] = True

    for cf in old_gwp.factors():
        for loc in cf.locations:
            new_gwp.characterize(flowable=cf.flowable, ref_quantity=cf.ref_quantity, context=cf.context,
                                 value=cf[loc], location=loc, origin=cf.origin)
    return new_gwp


def traci_2_biogenic_co2_only(traci, fg, external_ref='gwp_bio_co2_only', indicator='kg CO2-bio'):
    """
    Create a new method that *only* includes biogenic CO2 flows
    :param traci:
    :param fg:
    :param external_ref:
    :param indicator:
    :return:
    """
    try:
        return fg.get(external_ref)
    except EntityNotFound:
        pass

    old_gwp = traci.get('Global Warming Air')
    bio_c_only = fg.new_quantity('Global Warming Air - biogenic CO2 Only', ref_unit=indicator,
                                 external_ref=external_ref,
                                 Method=old_gwp['Method'], Category='Global Warming Air - only biogenic CO2',
                                 Indicator=indicator,
                                 uuid='2271523e-108f-4216-a65e-dac18ce3e83f',
                                 Comment='GWP from biogenic CO2 only (no other emissions included)',
                                 quell_biogenic_co2='only')
    old_gwp['quell_biogenic_co2'] = True

    co2 = fg.flowable('124-38-9')
    for cf in old_gwp.factors():
        if fg.flowable(cf.flowable) is co2:
            for loc in cf.locations:
                bio_c_only.characterize(flowable=cf.flowable, ref_quantity=cf.ref_quantity, context=cf.context,
                                        value=cf[loc], location=loc, origin=cf.origin)
    return bio_c_only
