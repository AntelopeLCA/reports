
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
    def __init__(self, fg, spanner, alloc_flow, external_ref=None):
        """
        We store the spanner
        :param fg: the foreground to contain the constructed fragments
        :param spanner: the multi-output model to be allocated
        :param alloc_flow: the flow (and reference quantity) to accumulate the allocated output
        :param external_ref: [None] default: 'allocator_[spanner.external_ref]_[alloc_flow.external_ref]'
        """
        self._fg = fg
        self._spanner = spanner
        self._alloc_flow = alloc_flow
        if external_ref is None:
            external_ref = 'allocator_%s_%s' % (self._spanner.external_ref, alloc_flow.external_ref)

        self._allocator = external_ref
        self._build_allocation_container()

    @property
    def alloc_flow(self):
        return self._alloc_flow

    @property
    def allocator(self):
        return self._fg[self._allocator]

    def _build_allocation_container(self):
        """
        Builds an Allocation fragment or "allocator": anchors the target spanner inside a superfragment, then catches
        all emerging allocatable outputs and casts them to an allocation flow.

        encapsulates the target activity inside a node, and then converts all
        allocatable outputs of the activity to their allocation quantity.
        - take the activity (spanner) to allocate
        - create a new fragment with the same reference flow
        - anchor it to the target spanner

        :return:
        """
        alloc_qty = self.alloc_flow.reference_entity

        if self.allocator is None:
            container = self._fg.new_fragment(flow=self._spanner.flow, direction=comp_dir(self._spanner.direction),
                                              exchange_value=self._spanner.cached_ev,
                                              external_ref=self._allocator)
        else:
            container = self.allocator

        self._fg.observe(container, exchange_value=self._spanner.observed_ev)
        container['alloc_flow'] = self.alloc_flow.link
        container.terminate(self._spanner)
        for c in self._spanner.cutoffs(True):
            if c.flow.cf(alloc_qty) != 0:
                try:
                    j = next(container.children_with_flow(c.flow))
                except StopIteration:
                    j = self._fg.new_fragment(c.flow, c.direction, parent=container)
                    self._fg.new_fragment(self.alloc_flow, c.direction, parent=j, balance=True)

                j.balance_flow.flow = self.alloc_flow

        return container

    def build_allocated_product(self, product_flow, direction='Output', external_ref=None, cap_activity=True):
        """
        This builds a single-output allocated production process for the named flow, using the previously
        constructed allocator.
        This caps off the facility activity flow and delivers a desired product flow with allocated burdens

        :param product_flow:
        :param direction: of product w.r.t allocated activity [default 'Output']
        :param external_ref: default: '[product_flow.external_ref]_alloc_[alloc_flow.external_ref]
        :param cap_activity: [True] conceal the allocator's activity share
        :return:
        """
        if external_ref is None:
            external_ref = '%s_alloc_%s' % (product_flow.external_ref, self.alloc_flow.external_ref)
        if self._fg[external_ref] is None:
            capsule = self._fg.new_fragment(flow=product_flow, direction=direction, exchange_value=1.0,
                                            external_ref=external_ref)
        else:
            capsule = self._fg[external_ref]
        self._fg.observe(capsule)
        if capsule.balance_flow is None:
            j = self._fg.new_fragment(flow=self.alloc_flow, direction=comp_dir(direction), parent=capsule, balance=True)
        else:
            j = capsule.balance_flow
            j.flow = self.alloc_flow
        j.terminate(self.allocator, term_flow=self.alloc_flow)

        if cap_activity:
            try:
                k = next(j.children_with_flow(self.allocator.flow))
            except StopIteration:
                k = self._fg.new_fragment(self.allocator.flow, direction=comp_dir(self.allocator.direction), parent=j)
            k.terminate(NullContext)
        else:
            try:
                k = next(j.children_with_flow(self.allocator.flow))
                self._fg.delete(k)
            except StopIteration:
                pass

        return capsule