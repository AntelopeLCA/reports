
from antelope_core.contexts import NullContext
from antelope import comp_dir


class AllocationEngine(object):
    """
    Creates an allocation framework for a spanner. By supplying an allocation flow (and a reference quantity), all
    cutoffs that are commensurable to the ref qty are cast into the allocation flow, and are aggregated during
    traversal. This fragment can be driven backwards (by anchoring to the allocation flow) to allocate the
    upstream impacts (and subsequent cut-offs).  This will emanate the spanner's reference flow in a fractional amount
    equal to the allocation share.

    Single-product wrappers then encapsulate that aggregator by terminating to the allocation flow, optionally capping
    off the allocation fraction.
    """


def build_allocation_container(fg, spanner, alloc_flow, external_ref=None):
    """
    Builds an Allocation fragment: anchors the target spanner inside a superfragment, then catches all emerging
    allocatable outputs and casts them to an allocation flow.

    encapsulates the target activity inside a node, and then converts all
    allocatable outputs of the activity to their allocation quantity.
    - take the activity (spanner) to allocate
    - create a new fragment with the same reference flow
    - anchor it to the target spanner

    :param fg:
    :param spanner:
    :param alloc_flow:
    :param external_ref:
    :return:
    """
    alloc_qty = alloc_flow.reference_entity
    if external_ref is None or fg[external_ref] is None:
        container = fg.new_fragment(flow=spanner.flow, direction=comp_dir(spanner.direction), exchange_value=spanner.cached_ev,
                                    external_ref=external_ref)
    else:
        container = fg[external_ref]
    fg.observe(container, exchange_value=spanner.observed_ev)
    container['alloc_flow'] = alloc_flow.link
    container.terminate(spanner)
    for c in spanner.cutoffs(True):
        if c.flow.cf(alloc_qty) != 0:
            try:
                j = next(container.children_with_flow(c.flow))
            except StopIteration:
                j = fg.new_fragment(c.flow, c.direction, parent=container)
                fg.new_fragment(alloc_flow, c.direction, parent=j, balance=True)
    return container


def build_allocated_product(fg, product_flow, alloc_container, external_ref=None):
    """
    Allocation capsule
    This caps off the facility activity flow and delivers a desired product flow with allocated burdens

    :param fg:
    :param product_flow:
    :param alloc_container:
    :param external_ref:
    :return:
    """
    alloc_flow = fg.get(alloc_container.get('alloc_flow'))
    if external_ref is None or fg[external_ref] is None:
        capsule = fg.new_fragment(flow=product_flow, direction='Output', exchange_value=1.0, external_ref=external_ref)
    else:
        capsule = fg[external_ref]
    fg.observe(capsule)
    if capsule.balance_flow is None:
        j = fg.new_fragment(flow=alloc_flow, direction='Input', parent=capsule, balance=True)
    else:
        j = capsule.balance_flow
        j.flow = alloc_flow
    j.terminate(alloc_container, term_flow=alloc_flow)
    try:
        k = next(j.children_with_flow(alloc_container.flow))
    except StopIteration:
        k = fg.new_fragment(alloc_container.flow, direction=comp_dir(alloc_container.direction), parent=j)
    k.terminate(NullContext)
    return capsule
