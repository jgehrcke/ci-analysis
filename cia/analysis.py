# MIT License

# Copyright (c) 2018-2020 Dr. Jan-Philip Gehrcke

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import logging
from datetime import timezone

import pandas as pd


log = logging.getLogger(__name__)


def calc_rolling_event_rate(
    series,
    window_width_seconds,
    upsample_with_zeros=False,
    upsample_with_zeros_until=None,
):
    """
    Require that Series index is a timestamp index.
    http://pandas.pydata.org/pandas-docs/version/0.19.2/api.html#window
    """
    assert isinstance(window_width_seconds, int)
    log.info(
        "Calculate event rate over rolling window (width: %s s)", window_width_seconds
    )

    # Each sample/item in the series corresponds to one event. The index value
    # is the datetime of the event (build), with a resolution of 1 second
    # (assumption about input). Multiple events per second are rare, but to be
    # expected: hence, get the number of events for any given second (group by
    # index value, and get the group size for each unique index value).
    eventcountseries = series.groupby(series.index).size()

    # Rename to `e` for the following transformations.
    e = eventcountseries

    log.info("raw event count series (raw series.groupby(series.index).size()):")
    print(e)

    n_minute_bins = 60
    log.info("downsample series into %s-minute bins", n_minute_bins)
    # Downsample the series into N-minute bins and sum the values falling into
    # a bin (counting the number of 'events' in this bin). Note(double-check,
    # but I think that's right): after this, the minimal time difference
    # between adjacent data points is `n_minute`s, and the maximal one is
    # unknown (can be large, this does not fill gaps).
    e = e.resample(f"{n_minute_bins}min").sum()
    # print(e)

    # The 'resample' before is not expected to upsample, just downsample. That
    # is, the resulting time index is expected to have gaps (where no events
    # occur in a time interval wider than the bin width above), Up-sample the
    # time index to fill these gaps, with a certain desired resolution and fill
    # the missing values with zeros. If desired.
    if upsample_with_zeros:
        if upsample_with_zeros_until is not None:
            if series.index.max() == upsample_with_zeros_until:
                log.info(
                    "calc_rolling_event_rate: last data point in series (%s) "
                    + "is equal to upsample_with_zeros_until (%s) -- skip",
                    series.index.max(),
                    upsample_with_zeros_until,
                )
            elif series.index.max() > upsample_with_zeros_until:
                log.error(
                    "calc_rolling_event_rate: last data point in series (%s) "
                    + "is newer than upsample_with_zeros_until (%s)",
                    series.index.max(),
                    upsample_with_zeros_until,
                )
                raise Exception("calc_rolling_event_rate: bad input (see error above)")

            else:
                # Construct additional data point as Series with 1 row.
                dp = pd.Series([0], index=[upsample_with_zeros_until])
                log.info(
                    "upsample_with_zeros_until mechanism: add data point to event count series: %s",
                    dp,
                )
                # print(f"e before: {e}")
                e = e.append(dp)
                # print(f"e after: {e}")
                # Example state after this extension: last to samples in `e`:
                #    2020-12-07 12:00:00+00:00    4
                #    2020-12-10 08:00:01+00:00    0

        log.info("upsample series (%s-minute bins) to fill gips, with 0", n_minute_bins)
        e = e.asfreq(f"{n_minute_bins}min", fill_value=0)
        # print(e)

    # Store point in time of newest data point in timeseries, needed later.
    # Note that this might be newer than the original `series.index.max()`, if
    # there was a `upsample_with_zeros_until`-based extension.
    datetime_newest_datapoint = e.index.max()
    log.info("newest data point in event count series: %s", datetime_newest_datapoint)

    # Construct Window object using `df.rolling()` whereas a time offset string
    # defines the rolling window width in seconds. Require N samples to be in
    # the moving window otherwise produce NaN?
    window = e.rolling(window="%sS" % window_width_seconds, min_periods=1)

    # Count the number of events (builds) within the rolling window.
    s = window.sum()

    # Normalize event count with/by the window width, yielding the average
    # build rate [Hz] in that time window.
    # rolling_build_rate = s / float(window_width_seconds)
    rolling_event_rate_d = 86400 * s / float(window_width_seconds)

    new_rate_column_name = "builds_per_day_%ss_window" % window_width_seconds
    rolling_event_rate_d.rename(new_rate_column_name, inplace=True)

    # In the resulting Series object, the request rate value is assigned to the
    # right window boundary index value (i.e. to the newest timestamp in the
    # window). For presentation and symmetry it is convenient and correct to
    # have it assigned (approximately) to the temporal center of the time
    # window. That makes sense for intuitive data interpretation of a single
    # rolling window time series, but is essential for meaningful presentation
    # of multiple rolling window series in the same plot -- keeping the
    # symmetry of original data is especially important when doing long term
    # analysis, with wide time windows with varying window width varies.
    # However: invoking `rolling(..., center=True)` however yields
    # `NotImplementedError: center is not implemented for datetimelike and
    # offset based windows`. As a workaround, shift the data by half the window
    # size to 'the left': shift the timestamp index by a constant / offset.
    offset = pd.DateOffset(seconds=window_width_seconds / 2.0)
    rolling_event_rate_d.index = rolling_event_rate_d.index - offset

    # In the resulting time series, all leftmost values up to the rolling
    # window width are dominated by the effect that the rolling window
    # (incoming from the left) does not yet completely overlap with the data.
    # That is, here the rolling window result is (linearly increasing)
    # systematically to small. Because by now the time series has one sample
    # per `n_minute_bins` minute, the number of leftmost samples with a bad
    # result corresponds to `int(window_width_seconds / (n_minute_bins * 60))`.
    # TODO: review this calc :)
    rolling_event_rate_d = rolling_event_rate_d[
        int(window_width_seconds / (n_minute_bins * 60)) :
    ]
    # print(rolling_event_rate_d)

    # Forward-fill the last value up to the last point in time of the original
    # time series (the newest data point in the rolling time window series
    # should be half a time window width older than that) -- that would be the
    # same as "plotting the window aggregate to the right edge of the window",
    # just that we didn't want to do so for the entire data interval (for
    # symmetry reasons, see above).
    apdx_last_value = rolling_event_rate_d.iloc[-1]

    # print(rolling_event_rate_d.index.max())
    # now = pd.Timestamp.now(tz=timezone.utc)
    apdx_index = pd.date_range(
        start=rolling_event_rate_d.index.max(),
        end=datetime_newest_datapoint,
        freq=f"{n_minute_bins}min",
    )
    apdx_series = pd.Series([apdx_last_value] * len(apdx_index), index=apdx_index)
    # print(apdx_index)
    # print(apdx_series)

    log.info(
        "rolling_event_rate_d: forward-fill to %s with last value %s",
        datetime_newest_datapoint,
        apdx_last_value,
    )
    rolling_event_rate_d = rolling_event_rate_d.append(apdx_series)

    # df.set_index("dt").reindex(r).fillna(0.0).rename_axis("dt").reset_index()

    # There's a lot of magic going on between how the datetime64 values
    # actually encode datetime in plots. Sharing an axis across (sub)plots is
    # brittle w.r.t. these differences. Work around this, here: make it so that
    # individual timestamps have a non-zero value for seconds, by simply adding
    # one second, shifting the whole data set by one second to the left. That
    # prevents, I guess, an optimization to hit in which would see that
    # individual timestamps hit the full hour or integer  multiples of 30 or 15
    # minutes. Also see
    # https://github.com/pandas-dev/pandas/issues/15874
    # https://github.com/pandas-dev/pandas/issues/15071
    # https://github.com/pandas-dev/pandas/issues/31074
    # https://github.com/pandas-dev/pandas/issues/29705
    # https://github.com/pandas-dev/pandas/issues/29719
    # https://github.com/pandas-dev/pandas/issues/18571
    # https://github.com/pandas-dev/pandas/issues/11574
    # https://github.com/pandas-dev/pandas/issues/22586
    # maybe also look at the index.resolution property to make this systematic.
    rolling_event_rate_d.index = rolling_event_rate_d.index + pd.to_timedelta("1 sec")

    # print(rolling_event_rate_d)

    return rolling_event_rate_d
