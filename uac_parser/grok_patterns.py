custom_patterns = {
    # Linux file permissions mode
    "MODE_AS_STRING": "[-dlbpcs][-rwxst]{9}",
    "MODE_AS_OCTAL": "[0124]?[0-7]{3}",
    # Network connection states
    "NETWORK_STATE": "(?i)(LISTEN|SYN_SENT|SYN_RECEIVED|ESTABLISHED|FIN_WAIT_1|FIN_WAIT_2|CLOSE_WAIT|CLOSING|LAST_ACK|TIME_WAIT|CLOSED|CONNECTED|LISTENING|CONNECTING|DISCONNECTED|UNCONN|ESTAB|CLOSE)",
    # IP address or wildcard
    "IP_OR_STAR": "(?:%{IP}|\\*)"
}

bodyfile_patterns = {
    # "bodyfile_v2": '%{DATA:md5}|(?<path>(?:\||[^|])*)|%{DATA:device}|%{DATA:inode}|%{DATA:mode_as_value}|%{DATA:mode_as_string}|%{NUMBER:num_of_links}|%{DATA:uid}|%{DATA:gid}|%{DATA:rdev}|%{NUMBER:size}|%{NUMBER:atime}|%{NUMBER:mtime}|%{NUMBER:ctime}|%{NUMBER:block_size}|%{NUMBER:num_of_blocks}',
    "bodyfile_v3": "^%{DATA:md5}\|%{UNIXPATH:file_path}\|%{DATA:inode}(\|%{MODE_AS_OCTAL:mode_as_octal})?\|%{MODE_AS_STRING:mode_as_string}\|%{DATA:uid}\|%{DATA:gid}\|%{NUMBER:size}\|%{NUMBER:atime}\|%{NUMBER:mtime}\|%{NUMBER:ctime}\|%{NUMBER:crtime}$"
}

process_patterns = {
    "PS_EF": r"(%{SPACE})?%{NUMBER:uid}\s+%{NUMBER:pid}\s+%{NUMBER:ppid}\s+%{NUMBER:cpu}\s+%{DATA:stime}\s+%{DATA:tty}\s+%{DATA:time}\s+%{GREEDYDATA:command}",
    "PS_AXO_PID_USER_LSTART_ARGS": "%{SPACE}%{NUMBER:pid}\s+%{USERNAME:user}\s+(?<started>%{DAY} %{MONTH} %{MONTHDAY} %{TIME} %{YEAR})\s+%{GREEDYDATA:command}",
}

network_patterns = {
    "NETSTAT_ANP_TCP": "^%{WORD:proto}\s+%{NUMBER}\s+%{NUMBER}\s+%{IP_OR_STAR:local_addr}[:.]%{DATA:local_port}\s+%{IP_OR_STAR:remote_addr}[:.]%{DATA:remote_port}\s+%{NETWORK_STATE:state}(\s+((%{NUMBER:pid}/%{DATA})|%{NUMBER:pid}))?\s*$",
    
    # macOS netstat -v format: dot-separated socket addresses (address.port)
    # Captures: proto, local_addr, local_port, remote_addr, remote_port, state, pid
    "NETSTAT_MAC_V": (
        "^%{WORD:proto}\\s+" +  # Protocol
        "%{NUMBER}\\s+%{NUMBER}\\s+" +  # Recv-Q, Send-Q
        "(?<local_addr>\\S+?)\\.(?<local_port>\\S+?)\\s+" +  # Local address.port
        "(?<remote_addr>\\S+?)\\.(?<remote_port>\\S+?)\\s+" +  # Remote address.port
        "%{NETWORK_STATE:state}.*?\\s+" +  # State
        "%{NUMBER:pid}\\s+.*$"  # PID
    ),
    
    # Linux ss format: colon-separated socket addresses (address:port)
    # Supports IPv6 with brackets: [::1]:port
    # Captures: proto (optional), local_addr, local_port, remote_addr, remote_port, state, pid (optional)
    "SS_LINUX": (
        "^(?:%{WORD:proto}\\s+)?" +  # Optional protocol
        "%{NETWORK_STATE:state}\\s+" +  # State
        "%{NUMBER}\\s+%{NUMBER}\\s+" +  # Recv-Q, Send-Q
        # Local socket: IPv6 [addr]:port or IPv4 addr:port
        "(?:(?:\\[(?<local_addr>[^\\]]+)\\]|(?<local_addr>[^:\\s]+)):(?<local_port>\\S+))\\s+" +
        # Remote socket: IPv6 [::]:*, IPv4 *:*, IPv6 [addr]:port, or IPv4 addr:port
        "(?:(?:\\[(?<remote_addr>[^\\]]+)\\]|(?<remote_addr>[^:\\s]+)):(?<remote_port>\\S+)|(?<remote_addr>\\*):(?<remote_port>\\*))" +
        "(?:.*?users:\\(\\(.*pid=%{NUMBER:pid}.*\\)\\))?.*$"  # Optional PID
    )
,
    
}


auth_patterns = {
    # last / lastb output — Linux and macOS/BSD
    #
    # Linux SSH:  elk_user  pts/0   192.168.1.1   Thu May 21 14:15   still logged in
    # macOS TTY:  adam      ttys005               Sat Nov 22 16:58   still logged in
    # macOS bare: reboot    time                  Sun Nov 16 19:25
    # Footer:     wtmp begins Sat Apr 11 16:49:50 2026   ← filtered in parser
    #
    # Key differences from the old pattern:
    #   %{NOTSPACE:tty}      — handles pts/0 (slash) as well as ttys005, console, time
    #   (?:\s+%{IP:source})? — optional source IP present on Linux SSH sessions, absent on macOS
    #   (?:\s+.*)?$          — trailing content (duration, "still logged in") is optional;
    #                          macOS reboot/shutdown lines end bare at the timestamp
    "LAST_LOGIN": (
        r"^%{NOTSPACE:username}\s+%{NOTSPACE:tty}"
        r"(?:\s+%{IP:source})?"
        r"\s+%{DAY:day}\s+%{MONTH:month}\s+%{MONTHDAY:monthday}"
        r"\s+%{HOUR:hour}:%{MINUTE:minute}(?::%{SECOND:second})?"
        r"(?:\s+.*)?$"
    ),
    
    "SSH_AUTH_SUCCESS": "^%{TIMESTAMP_ISO8601:timestamp}\.%{INT}(?:%{ISO8601_TIMEZONE:tz})\\s+%{DATA:hostname}\\s+%{DATA:provider}\\[%{NUMBER:pid}\\]:\\s+Accepted\\s+%{DATA:auth_method}\\s+for\\s+%{DATA:user}\\s+from\\s+%{IPORHOST:source}\\s+port\\s+%{INT}\\s%{DATA}(\\s+%{DATA:ssh_algo}\\s+%{DATA:fingerprint_algo}:%{DATA:fingerprint})?$"
}


command_history_patterns = {

    "SUDO_COMMAND": "^%{TIMESTAMP_ISO8601:timestamp}\\s+%{HOSTNAME:hostname}\\s+sudo(?:\\[%{NUMBER:pid}\\])?:\\s+%{USERNAME:username}\\s+:\\s+TTY=%{DATA:tty}\\s+;\\s+PWD=%{DATA:pwd}\\s+;\\s+USER=%{USERNAME:target_user}\\s+;\\s+COMMAND=%{GREEDYDATA:command}$",
}


user_patterns = {
    "ETC_PASSWD": "^%{USERNAME:user}:%{DATA:password_val}:%{INT:uid}:%{INT:gid}:%{GREEDYDATA:gecos}:%{UNIXPATH:home}:%{UNIXPATH:shell}$"
}