"""
Closely related to the stackbar compare, only we change our expectations for cases and units.
"""

import pandas as pd
import numpy as np
from matplotlib.cm import get_cmap
from matplotlib import pyplot as plt
from antelope_core.lcia_results import q_contrib, q_percent


def lcia_contribution_chart(df, indicator='Quantity', f_u='result', filename=None, _qs=None, stage_colors=None, colormap='viridis',
                            cmap_factor=1.0, wspace=0.3, percent=False):
    """
    "cases" is really quantities, and the only quantity is 'contrib'
    :param df:
    :param indicator: the column that contains the bar groups
    :param f_u:
    :param filename:
    :param _qs:
    :param stage_colors:
    :param colormap:
    :param cmap_factor:
    :param wspace:
    :param contrib:
    :return:
    """
    cases = []
    for i, k in df.iterrows():
        if k[indicator] not in cases:
            cases.append(k[indicator])

    # Pivot data to calculate stacked bar components
    # we want to preserve the order in the dataframe

    pivot_df = df.pivot_table(index=indicator, columns='Stage', values='Result', aggfunc='sum').fillna(
        0).reindex(cases)

    if percent:
        quantity = q_percent
        pivot_df = pivot_df.div(pivot_df.sum(axis=1) / 100, axis=0)

    else:
        quantity = q_contrib
        pivot_df = pivot_df.div(pivot_df.sum(axis=1), axis=0)

    stages = pivot_df.columns
    if stage_colors is None:
        _cm = get_cmap(colormap)
        stage_colors = {stage: _cm(i / len(stages) / cmap_factor) for i, stage in enumerate(stages)}

    # Create the figure with multiple axes
    fig, ax = plt.subplots(1, 1, figsize=(2 * len(cases), 6))
    plt.subplots_adjust(wspace=wspace)

    # Compute cumulative sums for stacking
    cumulative_sums = pivot_df.cumsum(axis=1)
    bar_positions = np.arange(len(cases))  # X positions for bars

    # Plot stacked bars
    for i, stage in enumerate(stages[::-1]):  # reverse direction for legend order
        ix = len(stages) - i - 2  # -1 for zero-indexing; -1 for cumsum offset
        bottom = cumulative_sums.iloc[:, ix] if ix >= 0 else None
        ax.bar(bar_positions, pivot_df[stage], label=stage, bottom=bottom, width=0.8,
               color=stage_colors[stage])

    # Customize the axes
    ax.set_title(f"{f_u}: {quantity.name}")
    ax.set_xlabel("Indicator")
    ax.set_ylabel(quantity.unit)
    ax.set_xlim([bar_positions[0] - 0.5, bar_positions[-1] + 0.5])
    ax.set_xticks(bar_positions)
    ax.set_xticklabels(cases, rotation=45)
    ax.legend(title="Stage", loc='upper left', bbox_to_anchor=(1, 1))

    # Set common y-label
    # fig.supylabel("Result")

    # Adjust layout
    # plt.tight_layout()
    if filename:
        plt.savefig(filename, bbox_inches='tight', dpi=300)
    return fig
