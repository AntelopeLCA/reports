"""
A common LCA use case: compare two different LCIA scores by stage

The interactive style:
 - identify the models
 - curate stages / groupings
 - build a model runner
 - spool out the results into a dataframe
 - send it here

"""

import pandas as pd
import numpy as np
from matplotlib.cm import get_cmap
from matplotlib import pyplot as plt
from math import ceil


def make_stack_plot_from_df(df, cases, f_u='result', filename=None, _qs=None, stage_colors=None, colormap='viridis',
                            cmap_factor=1.0, wspace=0.3, nrows=1):
    # Pivot data to calculate stacked bar components
    # we want to preserve the order in the dataframe
    if _qs is None:
        u_q = set(df['Quantity'])
        quantities = []
        units = []
        for i, k in enumerate(df['Quantity']):
            if k in u_q:
                quantities.append(k)
                u_q.remove(k)
                units.append(df['Unit'].loc[i])

            if len(u_q) == 0:
                break
    else:
        quantities = [q['ShortName'] for q in _qs]
        units = [q.unit for q in _qs]

    pivot_df = df.pivot_table(index=['Quantity', 'Case'], columns='Stage', values='Result', aggfunc='sum').fillna(
        0).reindex(
        pd.MultiIndex.from_product([quantities, cases], names=['Quantity', 'Case'])
    )

    # Unique indicators and stages
    stages = pivot_df.columns
    if stage_colors is None:
        _cm = get_cmap(colormap)
        stage_colors = {stage: _cm(i / len(stages) / cmap_factor) for i, stage in enumerate(stages)}

    # Create the figure with multiple axes
    # first, handle the subplot geometry
    n = min([nrows, len(quantities)])
    c = ceil(len(quantities) / n)

    fig, axes = plt.subplots(n, c, figsize=(5 * c, 6 * n), sharey=False, sharex=True)
    ax_legend = axes[0][-1]
    plt.subplots_adjust(wspace=wspace)

    if len(quantities) == 1:
        axes = [[axes]]  # Ensure axes is 2d array if only one plot
    else:
        axes = axes.reshape(1, n*c)  # this always returns a 2d array

    for ax in axes[0]:
        ax.set_axis_off()  # turn them all off

    # Loop through indicators to create subplots
    for ax, quantity, unit in zip(axes[0], quantities, units):
        # Filter data for this indicator
        indicator_data = pivot_df.loc[quantity]
        ax.set_axis_on()  # turn on when it's being used

        # Compute cumulative sums for stacking
        cumulative_sums = indicator_data.cumsum(axis=1).fillna(0)
        bar_positions = np.arange(len(cases))  # X positions for bars

        # Plot stacked bars
        for i, stage in enumerate(stages[::-1]):  # reverse direction for legend order
            ix = len(stages) - i - 2  # -1 for zero-indexing; -1 for cumsum offset
            bottom = cumulative_sums.iloc[:, ix] if ix >= 0 else None
            ax.bar(bar_positions, indicator_data[stage], label=stage, bottom=bottom, width=0.8,
                   color=stage_colors[stage])

        # Customize the axes
        ax.set_title(f"{f_u}: {quantity}")
        ax.set_xlabel(None)
        ax.set_ylabel(unit)
        ax.set_xlim([bar_positions[0] - 0.5, bar_positions[-1] + 0.5])
        ax.set_xticks(bar_positions)
        ax.set_xticklabels(cases, rotation=45)
        if ax is ax_legend:
            ax.legend(title="Stage", loc='upper left', bbox_to_anchor=(1, 1))

    # Set common y-label
    # fig.supylabel("Result")

    # Adjust layout
    # plt.tight_layout()
    if filename:
        plt.savefig(filename, bbox_inches='tight', dpi=300)
    return fig
