import argparse, os
import pandas as pd
import random

"""
For RQ2, ADMs were run on evaluation (hold-out) probes at a variety of alignment targets to collect probe responses.
Here, we post-construct N probe sets of 16 trinary probes (8 probes per attribute, AF & PS) based on random selection.
Separately, we post-construct N probe sets of 24 binary probes (8 probes per attribute, no MF) based on Latin square selection.
This script just creates the trinary probe sets, and outputs a csv file with the set information as input to the ingest script
that will collect the ADM responses from the database and run aligned vs. baseline alignment comparison across targets
and probe sets.

This is the high-level algorithm:
Import probe data from Excel.
For each attribute:
  Repeat until you have generated NUM_SETS valid 8-probe attribute-specific probe sets:
    Randomly choose a set of 8 distinct probe_ids from the probe data.
    If this probe set is already in the list of valid attribute probe sets, then throw out this attribute probe set.
  Display the list of probes sets for this attribute to stdout (plus some accounting data).
If requested, combine the attribute probe sets into NUM_SETS master 2D probe sets, and save it to a csv file.
"""

# These are constants that cannot be overridden via the command line
PROBES_PER_SET = 8
EVAL_NAME = 'june2026'
PROBEDATA_FILENAME = os.path.join('phase2', EVAL_NAME, 'RQ2-probes-trinary.xlsx')
OUTPUT_CSV_FILENAME = os.path.join('phase2', EVAL_NAME, 'RQ2-probesets-trinary.csv')

# These are default values that can be overridden via the command line
NUM_SETS = 25
VERBOSE = False # Useful for development and testing
ATTRIBUTES = ['AF', 'PS']
WRITE_FILES = True


"""
Generate NUM_SETS unique probe sets, of PROBES_PER_SET probes each, for the specified attribute.
"""
def generate_probe_sets(probe_data, attribute):
    probe_sets = set()
    duplicate_set_count = 0
    while len(probe_sets) < NUM_SETS:
        all_probe_ids = list(probe_data[attribute]['probe_id'])
        probe_set = random.sample(all_probe_ids, PROBES_PER_SET)

        if VERBOSE:
            print(f"Probe set has {len(probe_set)} probes.")

        probe_set = frozenset(probe_set)
        if probe_set in probe_sets:
            duplicate_set_count += 1
            if VERBOSE:
                print(f"Warning: Discarded duplicate set for setnum {setnum}: {probe_set}.")
        else:
            probe_sets.add(probe_set)
            print(f"Saving valid {attribute} probe set #{len(probe_sets)}.")
            if VERBOSE:
                print(f"  {probe_set}")
            if len(probe_sets) == NUM_SETS:
                break

    return probe_sets, duplicate_set_count


# Save probe sets for all attributes to a csv file.
def save_probe_sets_to_csv(all_probe_sets, file_path):
    data = []
    headers = []
    for setnum in range(NUM_SETS):
        data.append({})
        for item in all_probe_sets:
            attribute = item['attribute']
            probe_sets = item['probe_sets']
            probe_set = probe_sets[setnum]
            for i, probe_id in enumerate(probe_set):
                column_name = f'Probe-{attribute}{i+1}'
                data[setnum][column_name] = probe_id
                if setnum == 0: # Only write headers once
                    headers.append(column_name)

    # Create a DataFrame from the list of dictionaries
    df = pd.DataFrame(data)
    # Reorder the columns to match the desired headers
    df = df[headers]
    # Save to CSV
    df.to_csv(file_path, index=False)


"""
Construct N probe sets of 16 probes (8 probes per attribute) based random selection.
Displays the probe set info to stdout and outputs it to a csv file as input to a future ingest script.
"""
def main(attribute: str):
    attributes = [attribute] if attribute else ATTRIBUTES  # Make a set of attribute(s)
    print(f"Generating {NUM_SETS} random trinary probe sets for RQ2 for {attributes}.")

    # Load probe data
    probe_data = None
    print(f"Reading probe data from {PROBEDATA_FILENAME}.")
    try:
        probe_data = pd.read_excel(PROBEDATA_FILENAME, sheet_name=None)
    except Exception as e:
        print(f"An error occurred creating probe data: {e}.  Exiting.")
        exit(1)
    print('Done.')

    all_probe_sets = []
    for attr in attributes:
        print()
        print(f"Processing attribute {attr}.")
        probe_sets, duplicate_set_count = generate_probe_sets(probe_data, attr)

        # Output the probe sets
        print()
        print(f"Displaying {NUM_SETS} unique {PROBES_PER_SET}-probe {attr} probe sets:")
        for i, probe_set in enumerate(probe_sets):
            print(f"  Set{i+1}: " + ", ".join(map(str, probe_set)))

        print(f"Total duplicate sets: {duplicate_set_count}")

        # Add attribute probe sets to the master list of probe sets
        attr_probe_sets = [[probe_id for probe_id in probe_set] for probe_set in probe_sets]
        all_probe_sets.append({'attribute': attr, 'probe_sets': attr_probe_sets})

    print()
    print(f"Recombining attribute probe sets into master list of {NUM_SETS} probe sets.")
    # Save all probe sets to a CSV file, if requested
    if WRITE_FILES:
        save_probe_sets_to_csv(all_probe_sets, OUTPUT_CSV_FILENAME)
        print(f"Saving RQ2 trinary probe sets to {OUTPUT_CSV_FILENAME}")

    print("Done!")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate RQ2 probe sets')
    parser.add_argument('-n', '--numsets', type=int, required=False, default=NUM_SETS,
                        help=f"Number of sets (default {NUM_SETS})")
    parser.add_argument('-a', '--attribute', required=False, default=None,
                        help='Attribute of the probe set to generate (AF or PS), or all by default')
    parser.add_argument('-v', '--verbose', action='store_true', required=False, default=False,
                        help='Verbose logging')
    parser.add_argument('-no', '--no_output', action='store_true', required=False, default=False,
                        help='Do not write output file')
    args = parser.parse_args()

    attribute = None
    if args.numsets:
        NUM_SETS = args.numsets
    if args.attribute:
        if args.attribute.upper() not in ATTRIBUTES:
            parser.error(f"Invalid attribute; must be one of {ATTRIBUTES}.")
        attribute = args.attribute.upper()
    if args.verbose:
        VERBOSE = True
    if args.no_output:
        WRITE_FILES = False

    main(attribute)
