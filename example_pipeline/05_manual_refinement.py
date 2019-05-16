#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as plt

from somnotate._manual_state_annotation import TimeSeriesAnnotator

from data_io import (
    ArgumentParser,
    load_dataframe,
    check_dataframe,
    load_raw_signals,
    load_hypnogram,
    load_review_intervals,
    export_hypnogram,
)


from scipy.signal import welch


class VladsTimeSeriesAnnotator(TimeSeriesAnnotator):

    def __init__(self, callback, *args, **kwargs):
        self._callback = callback
        TimeSeriesAnnotator.__init__(self, *args, **kwargs)

    def _update_selection(self, *args, **kwargs):
        TimeSeriesAnnotator._update_selection(self, *args, **kwargs)
        self._callback(self.selection_lower_bound, self.selection_upper_bound)


if __name__ == '__main__':

    from matplotlib.gridspec import GridSpec

    from configuration import (
        state_annotation_signals,
        plot_raw_signals,
        state_to_color,
        state_display_order,
        keymap,
    )

    parser = ArgumentParser()
    parser.add_argument("spreadsheet_file_path", help="Use datasets specified in /path/to/spreadsheet.csv")
    args = parser.parse_args()

    # load spreadsheet / data frame
    datasets = load_dataframe(args.spreadsheet_file_path)

    # check contents of spreadsheet
    check_dataframe(datasets,
                    columns = [
                        'file_path_raw_signals',
                        'sampling_frequency_in_hz',
                        'file_path_automated_state_annotation',
                        'file_path_refined_state_annotation',
                        'file_path_review_intervals',
                    ] + state_annotation_signals,
                    column_to_dtype = {
                        'file_path_raw_signals' : str,
                        'sampling_frequency_in_hz' : (int, float, np.int, np.float, np.int64, np.float64),
                        'file_path_automated_state_annotation' : str,
                        'file_path_refined_state_annotation' : str,
                        'file_path_review_intervals' : str,
                    }
    )

    for ii, dataset in datasets.iterrows():

        print("{} ({}/{})".format(dataset['file_path_raw_signals'], ii+1, len(datasets)))

        # load data
        total_raw_signals = len(state_annotation_signals)
        signal_labels = [dataset[column_name] for column_name in state_annotation_signals]
        raw_signals = load_raw_signals(dataset['file_path_raw_signals'], signal_labels)
        predicted_states, predicted_intervals = load_hypnogram(dataset['file_path_automated_state_annotation'])
        review_intervals, review_scores = load_review_intervals(dataset['file_path_review_intervals'])

        # callback
        psd_fig, axes = plt.subplots(1, total_raw_signals, sharex=True, sharey=True)
        lines = []
        for ii, (signal, ax) in enumerate(zip(raw_signals.T, axes)):
            frequencies, psd = welch(signal, dataset['sampling_frequency_in_hz'])
            line, = ax.plot(frequencies, psd)
            lines.append(line)
            ax.set_xlabel("Frequency [Hz]")
        axes[0].set_ylabel("Power")

        def callback(selection_lower_bound, selection_upper_bound):
            start = int(dataset['sampling_frequency_in_hz'] * selection_lower_bound)
            stop  = int(dataset['sampling_frequency_in_hz'] * selection_upper_bound)
            for ii, (signal, line) in enumerate(zip(raw_signals.T, lines)):
                frequencies, psd = welch(signal[start:stop], dataset['sampling_frequency_in_hz'])
                line.set_data(frequencies, psd)
            psd_fig.canvas.draw()

        # compute order for regions of interest
        order = np.argsort(review_scores)[::-1]
        regions_of_interest = review_intervals[order]

        # initialise figure
        fig = plt.figure()
        gs = GridSpec(4, 1)
        data_axis  = fig.add_subplot(gs[:3, 0])
        state_axis = fig.add_subplot(gs[3, 0], sharex=data_axis)
        state_axis.set_xlabel('Time [s]')

        # plot signals
        plot_raw_signals(
            raw_signals,
            sampling_frequency = dataset['sampling_frequency_in_hz'],
            ax                 = data_axis,
        )

        # initialise annotator
        annotator = VladsTimeSeriesAnnotator(callback, data_axis, state_axis, keymap,
                                        interval_to_state   = zip(predicted_intervals, predicted_states),
                                        regions_of_interest = regions_of_interest,
                                        state_to_color      = state_to_color,
                                        state_display_order = state_display_order,
        )
        fig.tight_layout()
        plt.show()

        refined_intervals = list(annotator.interval_to_state.keys())
        refined_states = list(annotator.interval_to_state.values())
        export_hypnogram(dataset['file_path_refined_state_annotation'], refined_states,
                         refined_intervals)
