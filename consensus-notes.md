#### Links

https://gitweb.torproject.org/torspec.git/tree/dir-spec.txt
https://research.torproject.org/techreports/data-2011-03-14.pdf <- Just points to spec
https://research.torproject.org/techreports/bufferstats-2009-08-25.pdf

#### Total Bytes?

    "read-history" YYYY-MM-DD HH:MM:SS (NSEC s) NUM,NUM,NUM,NUM,NUM... NL
        [At most once]
    "write-history" YYYY-MM-DD HH:MM:SS (NSEC s) NUM,NUM,NUM,NUM,NUM... NL
        [At most once]

        Declare how much bandwidth the OR has used recently. Usage is divided
        into intervals of NSEC seconds.  The YYYY-MM-DD HH:MM:SS field
        defines the end of the most recent interval.  The numbers are the
        number of bytes used in the most recent intervals, ordered from
        oldest to newest.

#### Entry Stats

    "entry-stats-end" YYYY-MM-DD HH:MM:SS (NSEC s) NL
        [At most once.]

        YYYY-MM-DD HH:MM:SS defines the end of the included measurement
        interval of length NSEC seconds (86400 seconds by default).

        An "entry-stats-end" line, as well as any other "entry-*"
        line, is first added after the relay has been running for at least
        24 hours.

    "entry-ips" CC=NUM,CC=NUM,... NL
        [At most once.]

        List of mappings from two-letter country codes to the number of
        unique IP addresses that have connected from that country to the
        relay and which are no known other relays, rounded up to the
        nearest multiple of 8.

#### Cell Stats

    "cell-stats-end" YYYY-MM-DD HH:MM:SS (NSEC s) NL
        [At most once.]

        YYYY-MM-DD HH:MM:SS defines the end of the included measurement
        interval of length NSEC seconds (86400 seconds by default).

        A "cell-stats-end" line, as well as any other "cell-*" line,
        is first added after the relay has been running for at least 24
        hours.

    "cell-processed-cells" NUM,...,NUM NL
        [At most once.]

        Mean number of processed cells per circuit, subdivided into
        deciles of circuits by the number of cells they have processed in
        descending order from loudest to quietest circuits.

    "cell-queued-cells" NUM,...,NUM NL
        [At most once.]

        Mean number of cells contained in queues by circuit decile. These
        means are calculated by 1) determining the mean number of cells in
        a single circuit between its creation and its termination and 2)
        calculating the mean for all circuits in a given decile as
        determined in "cell-processed-cells". Numbers have a precision of
        two decimal places.

        Note that this statistic can be inaccurate for circuits that had
        queued cells at the start or end of the measurement interval.

    "cell-time-in-queue" NUM,...,NUM NL
        [At most once.]

        Mean time cells spend in circuit queues in milliseconds. Times are
        calculated by 1) determining the mean time cells spend in the
        queue of a single circuit and 2) calculating the mean for all
        circuits in a given decile as determined in
        "cell-processed-cells".

        Note that this statistic can be inaccurate for circuits that had
        queued cells at the start or end of the measurement interval.

    "cell-circuits-per-decile" NUM NL
        [At most once.]

        Mean number of circuits that are included in any of the deciles,
        rounded up to the next integer.

#### Connection Stats

    "conn-bi-direct" YYYY-MM-DD HH:MM:SS (NSEC s) BELOW,READ,WRITE,BOTH NL
        [At most once]

        Number of connections, split into 10-second intervals, that are
        used uni-directionally or bi-directionally as observed in the NSEC
        seconds (usually 86400 seconds) before YYYY-MM-DD HH:MM:SS.  Every
        10 seconds, we determine for every connection whether we read and
        wrote less than a threshold of 20 KiB (BELOW), read at least 10
        times more than we wrote (READ), wrote at least 10 times more than
        we read (WRITE), or read and wrote more than the threshold, but
        not 10 times more in either direction (BOTH).  After classifying a
        connection, read and write counters are reset for the next
        10-second interval.

#### Exit Stats

    "exit-stats-end" YYYY-MM-DD HH:MM:SS (NSEC s) NL
        [At most once.]

        YYYY-MM-DD HH:MM:SS defines the end of the included measurement
        interval of length NSEC seconds (86400 seconds by default).

        An "exit-stats-end" line, as well as any other "exit-*" line, is
        first added after the relay has been running for at least 24 hours
        and only if the relay permits exiting (where exiting to a single
        port and IP address is sufficient).

    "exit-kibibytes-written" port=N,port=N,... NL
        [At most once.]
    "exit-kibibytes-read" port=N,port=N,... NL
        [At most once.]

        List of mappings from ports to the number of kibibytes that the
        relay has written to or read from exit connections to that port,
        rounded up to the next full kibibyte.  Relays may limit the
        number of listed ports and subsume any remaining kibibytes under
        port "other".

    "exit-streams-opened" port=N,port=N,... NL
        [At most once.]

        List of mappings from ports to the number of opened exit streams
        to that port, rounded up to the nearest multiple of 4.  Relays may
        limit the number of listed ports and subsume any remaining opened
        streams under port "other".