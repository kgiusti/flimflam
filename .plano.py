#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

from flimflam import *

standard_parameters = (
    CommandParameter("relay", default="skrouterd", positional=False,
                     help="The intermediary standing between the workload client and server"),
    CommandParameter("workload", default="builtin", positional=False, short_option="w",
                     help="The selected workload"),
    CommandParameter("jobs", default=2, type=int, positional=False,
                     help="The number of concurrent workload jobs"),
    CommandParameter("warmup", default=5, type=int, positional=False, metavar="SECONDS",
                     help="The warmup time in seconds"),
    CommandParameter("duration", default=5, type=int, positional=False, metavar="SECONDS",
                     help="The execution time (excluding warmup) in seconds"),
)

@command
def check(ignore_perf_config=False):
    """
    Check for required programs and system configuration
    """

    check_program("gcc", "I can't find gcc.  Run 'dnf install gcc'.")
    check_program("perf", "I can't find the perf tools.  Run 'dnf install perf'.")
    check_program("pidstat", "I can't find pidstat.  Run 'dnf install sysstat'.")
    check_program("taskset", "I can't find taskset.  Run 'dnf install util-linux-core'.")

    if not ignore_perf_config:
        perf_event_paranoid = read("/proc/sys/kernel/perf_event_paranoid")

        if perf_event_paranoid != "-1\n":
            exit("Perf events are not enabled.  Run 'echo -1 > /proc/sys/kernel/perf_event_paranoid' as root.")

    print_heading("Note!")
    print("To reliably get stack traces, it is important to compile with frame pointers.")
    print("Use CFLAGS=-fno-omit-frame-pointer when compiling.")
    print()

@command
def build():
    """
    Compile the builtin workload
    """

    check_program("gcc", "I can't find gcc.  Run 'dnf install gcc'.")

    run("gcc client.c -o client -g -O2 -std=c99 -fno-omit-frame-pointer")
    run("gcc server.c -o server -g -O2 -std=c99 -fno-omit-frame-pointer")

def run_and_print_summary(kwargs, capture=None):
    if capture is None:
        def capture(pid1, pid2, duration):
            sleep(duration)

    runner = Runner(kwargs)

    output_dir = runner.run(capture)

    runner.print_summary()

    return output_dir

@command(parameters=standard_parameters)
def run_(*args, **kwargs):
    """
    Run the workload and relays without capturing perf data
    """

    build()

    run_and_print_summary(kwargs)
    print()

@command(parameters=standard_parameters)
def stat(*args, **kwargs):
    """
    Capture 'perf stat' output
    """

    build()

    with temp_file() as output:
        def capture(pid1, pid2, duration):
            run(f"perf stat --detailed --pid {pid1},{pid2} sleep {duration}", output=output)

        run_and_print_summary(kwargs, capture)
        print(read(output))

@command(parameters=standard_parameters)
def skstat(*args, **kwargs):
    """
    Capture 'skstat' output
    """

    if kwargs["relay"] != "skrouterd":
        fail("The skstat command works with skrouterd only")

    build()

    with temp_file() as output1, temp_file() as output2:
        def capture(pid1, pid2, duration):
            sleep(duration)
            run(f"skstat -b localhost:56721 -m", stdout=output1)
            run(f"skstat -b localhost:56722 -m", stdout=output2)

        run_and_print_summary(kwargs, capture)

        print_heading("Router 1")
        print(read(output1))
        print_heading("Router 2")
        print(read(output2))

@command(parameters=standard_parameters)
def record(*args, **kwargs):
    """
    Capture perf events using 'perf record'
    """

    build()

    def capture(pid1, pid2, duration):
        run(f"perf record --freq 997 --call-graph fp --pid {pid1},{pid2} sleep {duration}")

    run_and_print_summary(kwargs, capture)

    print_heading("Next step")
    print("Run 'perf report --no-children'")
    print()

@command(parameters=standard_parameters)
def c2c(*args, **kwargs):
    """
    Capture perf events using 'perf c2c'
    """

    build()

    def capture(pid1, pid2, duration):
        run(f"perf c2c record --freq 997 --call-graph fp --pid {pid1},{pid2} sleep {duration}")

    run_and_print_summary(kwargs, capture)

    print_heading("Next step")
    print("Run 'perf c2c report'")
    print()

@command(parameters=standard_parameters)
def mem(*args, **kwargs):
    """
    Capture perf events using 'perf mem'
    """

    build()

    def capture(pid1, pid2, duration):
        run(f"perf mem record --freq 997 --call-graph fp --pid {pid1},{pid2} sleep {duration}")

    run_and_print_summary(kwargs, capture)

    print_heading("Next step")
    print("Run 'perf mem report --no-children'")
    print()

@command(parameters=standard_parameters)
def flamegraph(*args, **kwargs):
    """
    Generate a flamegraph
    """

    try:
        check_exists("/usr/share/d3-flame-graph")
    except:
        fail("I can't find d3-flame-graph.  Run 'dnf install js-d3-flame-graph'.")

    build()

    if exists("flamegraph.html"):
        move("flamegraph.html", "old.flamegraph.html")

    def capture(pid1, pid2, duration):
        run(f"perf script flamegraph --freq 997 --call-graph fp --pid {pid1},{pid2} sleep {duration}")

    run_and_print_summary(kwargs, capture)

    print_heading("Next step")

    print("Go to {} in your browser".format(get_file_url("flamegraph.html")))
    print()

@command(parameters=standard_parameters[2:])
def bench(*args, **kwargs):
    """
    Run each workload on each relay and summarize the results
    """

    build()

    data = [["Workload", "Relay", "Bits/s", "Ops/s", "R1 CPU", "R1 RSS", "R2 CPU", "R2 RSS"]]

    for workload in workloads:
        for relay in relays:
            kwargs["relay"] = relay
            kwargs["workload"] = workload

            output_dir = run_and_print_summary(kwargs)
            print()

            summary = read_json(join(output_dir, "summary.json"))
            results = summary["results"]
            bps = None
            ops = None

            if "octets" in results:
                bps = format_quantity(results["octets"] * 8 / results["duration"])

            if "operations" in results:
                ops = format_quantity(results["operations"] / results["duration"])

            if "resources" in summary:
                r1cpu = format_percent(summary["resources"]["relay_1"]["average_cpu"])
                r1rss = format_quantity(summary["resources"]["relay_1"]["max_rss"], mode="binary")
                r2cpu = format_percent(summary["resources"]["relay_2"]["average_cpu"])
                r2rss = format_quantity(summary["resources"]["relay_2"]["max_rss"], mode="binary")
            else:
                r1cpu, r1rss, r2cpu, r2rss = None, None, None, None

            data.append([workload, relay, bps, ops, r1cpu, r1rss, r2cpu, r2rss])

    print("---")
    print_heading("Benchmark results")
    print_table(data, "llr")
    print()

@command
def clean():
    """
    Remove build artifacts and output files
    """

    remove("client")
    remove("server")
    remove("perf.data")
    remove("perf.data.old")
    remove("flamegraph.html")
    remove("old.flamegraph.html")
    remove(list_dir(".", "transfers.*.csv"))
    remove(find(".", "__pycache__"))

@command(hidden=True)
def self_test():
    for name in "flamegraph", "stat", "record", "c2c", "mem", "skstat":
        globals()[name](relay="skrouterd", workload="builtin", duration=1, warmup=1, jobs=1)

    for relay in relays.keys():
        run_(relay=relay, workload="builtin", duration=1, warmup=1, jobs=1)

    for workload in workloads.keys():
        run_(relay="none", workload=workload, duration=1, warmup=1, jobs=1)

    clean()
