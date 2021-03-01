# ci-analysis

🛠️🪛
🗜️⚙️
🔩🔨


## Example

A figure created with this tool:

![alt text](https://i.imgur.com/t71VpG4.png)

Command run to create this figure, and its (shortened) output:

```text
$ export BUILDKITE_API_TOKEN="..."
$ ci-analysis bk opstrace scheduled-main-builds \
  --ignore-builds-longer-than 5000 \
  --ignore-builds-before 2020-08-15 \
  --multi-plot-only

...

210301-12:14:40.238 INFO: loading data from file: opstrace_scheduled-main-builds.pickle.cache
210301-12:14:40.303 INFO: read 39.25 MiB
210301-12:14:40.691 INFO: loaded 2946 builds from disk
210301-12:14:40.691 INFO: newest build number in cache: 1236
210301-12:14:40.691 INFO: update (forward-fill)
210301-12:14:40.691 INFO: fetch builds: get first page (newest builds first)
210301-12:14:44.727 INFO: got 100 builds in paginated response
...
210301-12:15:04.543 INFO: builds_resp.next_page: 7
210301-12:15:08.805 INFO: got 100 builds in paginated response
210301-12:15:08.805 INFO: current page contains build 1236 and older -- drop, stop fetching
210301-12:15:08.806 INFO: fetched data for 600 finished builds
210301-12:15:08.806 INFO: newest build number / oldest build number: 1836 /1237
210301-12:15:08.808 INFO: persist to disk (pickle cache): combination of previous cache and newly fetched builds
210301-12:15:09.325 INFO: persist 51547258 byte(s) (49.16 MiB) to file opstrace_scheduled-main-builds.pickle.cache
210301-12:15:09.386 INFO: process 3546 builds, rewrite meta data
...
210301-12:15:09.597 INFO:

perform build stability analysis (from all builds, passed builds) -- window_width_days: 4
210301-12:15:09.597 INFO: build pandas dataframe for passed builds
...
210301-12:15:09.746 INFO: build histogram: which step (key) was executed how often?
210301-12:15:09.753 INFO: top 7 executed build steps (by step key)


|     step key      | number of executions |
|-------------------|---------------------:|
| preamble          |                 1832 |
| maintest-gcp      |                 1832 |
| maintest-aws      |                 1832 |
| cleanup-tmp       |                 1605 |
| check-docs        |                 1570 |
| publish-artifacts |                  981 |
| unit-tests        |                  619 |

210301-12:15:09.829 INFO: build pandas dataframe for passed builds
...
210301-12:15:11.497 INFO: Writing PNG figure to 2021-03-01_report/2021-03-01_multiplot-summary.png
```




## Notes

Analysis methods re-use ideas from my previous projects:

* https://github.com/jgehrcke/dcos-dev-prod-analysis
* https://github.com/jgehrcke/bouncer-log-analysis
* https://github.com/jgehrcke/goeffel
