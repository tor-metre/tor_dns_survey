import argparse
from relay_perf import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Tor Metre Relay Observatory')
    parser.add_argument('--mode', choices=['exits', 'guards', 'one-hop'], required=True,
                        help="The type of measurements to perform")
    parser.add_argument('--instance', choices=['one', 'two', 'three', 'four'], required=True,
                        help="The tor instance to use, must be unique and created with tor-instance-create. User must be part of correct group")
    parser.add_argument('--database',default="measurements.db",help="The database to use")
    args = parser.parse_args()
    main(args)