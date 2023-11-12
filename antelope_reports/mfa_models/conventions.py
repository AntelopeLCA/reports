def transport_model(modeled_flow):
    return 'Transport Mix - %s' % modeled_flow.name


def activity_model_ref(modeled_fragment):
    n = 'Activity model - %s (%s)' % (modeled_fragment['Name'], modeled_fragment.get('scope'))
    n = n.replace('/', '_')
    return n


def logistics_summary_ref(sc_frag):
    return '%s Logistics' % sc_frag.name
