import argparse, os
import numpy as np
import pandas as pd
import random
from scipy.stats import pearsonr

"""
For RQ2, ADMs will be run on evaluation (hold-out) probes at a variety of alignment targets to collect probe responses.
We post-construct N probe sets of 32 probes (8 probes per attribute) based on Latin square selection.
This PR just creates the probe sets, and outputs a csv file with the set information as input to the ingest script
that will collect the ADM responses from the database and run aligned vs. baseline alignment comparison across targets
and probe sets.

This is the high-level algorithm:
Import bucket (bin) data from Excel.
Import probe data from Excel.
For each attribute:
  Repeat until you have generated NUM_SETS valid 8-probe attribute-specific probe sets:
    Generate an NxN Latin square where the order of the square is the number of probes in each set (PROBES_PER_SET).
    For each set number (i.e., condition) in the Latin square:
      Generate a coordinate set, i.e., a (row, column) coordinate of the specified condition.
      For each coordinate in the set:
        Look up the list of medical and attribute deltas for the given medical/attribute bucket specified by the coordinate.
          If a bucket is empty, choose from the previous bucket; if the first bucket is empty, choose from the next bucket.
        Select a random probe ID from the list of probe IDs from the specified buckets, replacing those already in the set if possible, and add it to the set.
      If this probe set doesn't have PROBES_PER_SET probes (because there weren't enough probe IDs in a given medical/attribute pair),
        then supplement with a probe ID from another bucket until you have PROBES_PER_SET probes in the set.
      If this probe set is already in the list of valid attribute probe sets, then throw out this attribute probe set.
      If the medical deltas and attribute deltas are correlated, then throw out this attribute probe set.
  Display the list of probes sets for this attribute to stdout (plus some accounting data).
If requested, combine the attribute probe sets into NUM_SETS master 4D probe sets, and save it to a csv file.
"""

# These are constants that cannot be overridden via the command line
PROBES_PER_SET = 8
EVAL_NAME = 'feb2026'
BUCKET_FILENAME = os.path.join('phase2', EVAL_NAME, 'RQ2-buckets.xlsx')
PROBEDATA_FILENAME = os.path.join('phase2', EVAL_NAME, 'RQ2-probes.xlsx')
OUTPUT_CSV_FILENAME = os.path.join('phase2', EVAL_NAME, 'RQ2-probesets.csv')

# These are default values that can be overridden via the command line
NUM_SETS = 25
VERBOSE = False # Useful for development and testing
ATTRIBUTES = ['AF', 'MF', 'SS', 'PS']
WRITE_FILES = True

# Convert Excel data to a list of buckets/bins
def import_buckets(file_path):
    # Read all sheets into a dictionary of DataFrames
    df_dict = pd.read_excel(file_path, sheet_name=None)
    results = {}

    for sheet_name, df in df_dict.items():
        # Check for the presence of the delimiter right away
        delimiter_row = None
        for index, row in df.iterrows():
            if 'Attribute buckets' in row.values:
                delimiter_row = index
                break

        if delimiter_row is None:
            raise Exception(f"Delimiter 'Attribute buckets' not found in sheet '{sheet_name}'.")

        medical_deltas = []
        attribute_deltas = []

        # Split the DataFrame into two parts
        medical_deltas_df = df.iloc[:delimiter_row]
        attribute_deltas_df = df.iloc[delimiter_row+1:]

        # Function to split comma-separated values and convert to floats
        def split_and_convert_to_floats(values, index):
            if pd.isna(values[index]) or values[index] == '':
                if index == 0:  # If the first value is empty, use the next row's value
                    return split_and_convert_to_floats(values, index + 1)
                else:  # Use the previous row's value
                    return split_and_convert_to_floats(values, index - 1)

            try:
                # Check if the value is a single float
                if isinstance(values[index], (int, float)):
                    return [float(values[index])]
                # Otherwise, split and convert to floats
                return [float(v.strip()) for v in str(values[index]).split(',')]
            except ValueError as e:
                raise Exception(f"{values[index]}")

        # Extract the second column as a list of lists for each part
        try:
            medical_deltas = [split_and_convert_to_floats(medical_deltas_df.iloc[:, 1].values, i) for i in range(len(medical_deltas_df))]
            attribute_deltas = [split_and_convert_to_floats(attribute_deltas_df.iloc[:, 1].values, i) for i in range(len(attribute_deltas_df))]
        except Exception as e:
            raise Exception(f"Error converting values to floats in sheet '{sheet_name}': {e}")

        results[sheet_name] = {
            'medical_deltas': medical_deltas,
            'attribute_deltas': attribute_deltas
        }

    return results


def generate_random_latin_square(n):
    """
    Written by Chrome/Gemini.

    Generates a random Latin square of order n using a base square
    and shuffling rows/columns.

    A Latin square is an n x n array filled with n different symbols,
    each occurring exactly once in each row and once in each column.

    Args:
        n (int): The order (size) of the Latin square.

    Returns:
        numpy.ndarray: A randomly generated Latin square.
    """
    if n <= 0:
        raise ValueError("Order n must be a positive integer.")

    base_square = np.arange(n)
    latin_square = np.array([(base_square + i) % n for i in range(n)])

    # Randomly shuffle the rows
    np.random.shuffle(latin_square)

    # Randomly shuffle the columns
    latin_square = latin_square.T
    np.random.shuffle(latin_square)
    latin_square = latin_square.T

    latin_square += 1  # Convert to 1-based indexing
    return latin_square


def generate_coordinate_set(latin_square, setnum):
    """
    Generates a set of coordinates from a Latin square for a given set number.
    A set number is a condition in the Latin square, one per order of the Latin square.

    Args:
        latin_square (numpy.ndarray): The Latin square.
        setnum (int): The set number to extract coordinates for.

    Returns:
        list: A list of coordinate tuples (row, column).
    """
    coordinates = []
    size = latin_square.shape[0]
    for r in range(size):
        c = np.where(latin_square[r] == setnum)[0][0]
        coordinates.append((r + 1, c + 1))  # Convert to 1-based indexing (row, column)
    return coordinates


# Function to select a random probe_id from among the specified medical and attribute deltas
# Returns the probe_id and the randomly selected medical and attribute delta.
def select_probeid_from_deltas(med_deltas, attr_deltas, probe_data):
    selected_med_delta = random.choice(med_deltas)
    selected_attr_delta = random.choice(attr_deltas)
    filtered_data = probe_data[
        (probe_data['med_delta'] == selected_med_delta) &
        (probe_data['attr_delta'] == selected_attr_delta)
    ]

    probe_ids = filtered_data['probe_id'].tolist()
    return random.choice(probe_ids), selected_med_delta, selected_attr_delta


# Returns the medical and attribute deltas specified by coordinate.
def convert_coordinate_to_deltas(coordinate: list, buckets):
    if VERBOSE:
        print(f"  Medical deltas: {buckets[0]}")
        print(f"  Attribute deltas: {buckets[1]}")
    return buckets[0][coordinate[0]-1], buckets[1][coordinate[1]-1]


def is_correlated(list1, list2):
    """
    Checks if the given set of lists is correlated using Pearson correlation.

    Args:
        list1: A list of floats.
        list2: A list of floats.

    Returns:
        bool: True if the absolute value of the Pearson correlation coefficient is >= 0.2, False otherwise.
    """
    correlation_coeff, _ = pearsonr(list1, list2)
    return abs(correlation_coeff) >= 0.2


"""
Process a single coordinate of the Latin square:
  Look up the list of medical and attribute deltas for the given medical/attribute bucket specified by the coordinate.
  Select a random probe ID from the list of probe IDs from the specified buckets, replacing those already in the set if possible.
  Return the probe ID and its associated medical and attribute delta.
"""
def process_coordinate(coordinate, probe_set, bucket_data, probe_data, attribute):
    if VERBOSE:
        print(f"Processing coordinate {coordinate}:")
    med_deltas, attr_deltas = convert_coordinate_to_deltas(coordinate, bucket_data[attribute])
    if VERBOSE:
        print(f"  Coordinate deltas: {med_deltas} / {attr_deltas}")
    probe_id = None
    med_delta = None
    attr_delta =  None
    already_found_dup = False
    while not probe_id:
        probe_id, med_delta, attr_delta = select_probeid_from_deltas(med_deltas, attr_deltas, probe_data[attribute])
        if VERBOSE:
            print(f"  Randomly selected probe_id {probe_id} with med delta {med_delta} and attr delta {attr_delta}")
        if probe_id in probe_set:
            if already_found_dup:
                if VERBOSE:
                    print(f"--> Found another duplicate probe {probe_id}. Skipping this coordinate")
                return None, None, None
            else:
                if VERBOSE:
                    print(f"--> Discarding duplicate probe {probe_id}.")
                probe_id = None
                already_found_dup = True # Only try to replace a dup once, because there might not be any non-dups left

    return probe_id, med_delta, attr_delta


"""
Generate NUM_SETS probe sets, of PROBES_PER_SET probes each, for the specified attribute.
The probe sets will be unique and the medical and attribute deltas of the probes will not be correlated.
"""
def generate_probe_sets(bucket_data, probe_data, attribute):
    probe_sets = set()
    duplicate_set_count = 0
    correlated_set_count = 0
    supplemented_set_count = 0
    while len(probe_sets) < NUM_SETS:
        print("Generating Latin Square.")
        latin_square = generate_random_latin_square(PROBES_PER_SET)
        if VERBOSE:
            print(latin_square)

        for setnum in range(1, PROBES_PER_SET + 1):  # 1 to LATIN_SQUARE_ORDER
            coordinates = generate_coordinate_set(latin_square, setnum)
            if VERBOSE:
                print(f"Coordinates: {coordinates}")

            probe_set = set()
            set_med_deltas = []
            set_attr_deltas = []
            for coordinate in coordinates:
                probe_id, med_delta, attr_delta = process_coordinate(coordinate, probe_set, bucket_data, probe_data, attribute)
                if probe_id: # Sometimes there aren't enough probes in a given coordinate
                    probe_set.add(probe_id)
                    set_med_deltas.append(med_delta)
                    set_attr_deltas.append(attr_delta)

            if VERBOSE:
                print(f"Probe set has {len(probe_set)} probes.")
            is_supplemented = False
            while len(probe_set) < PROBES_PER_SET:
                is_supplemented = True
                if VERBOSE:
                    print(f"Adding random probe to small ({len(probe_set)}) {attribute} probe set.")
                coordinate = [random.randint(1, PROBES_PER_SET), random.randint(1, PROBES_PER_SET)]
                if VERBOSE:
                    print(f"  Trying new coordinate {coordinate}.")
                probe_id, med_delta, attr_delta = process_coordinate(coordinate, probe_set, bucket_data, probe_data, attribute)
                if probe_id: # Sometimes there aren't enough probes in a given coordinate
                    probe_set.add(probe_id)
                    set_med_deltas.append(med_delta)
                    set_attr_deltas.append(attr_delta)

            probe_set = frozenset(probe_set)
            if probe_set in probe_sets:
                duplicate_set_count += 1
                if VERBOSE:
                    print(f"Warning: Discarded duplicate set for setnum {setnum}: {probe_set}.")
            elif is_correlated(set_med_deltas, set_attr_deltas):
                correlated_set_count += 1
                if VERBOSE:
                    print(f"Warning: Discarded correlated set for setnum {setnum}: {probe_set} because {set_med_deltas} is correlated with {set_attr_deltas}")
            else:
                probe_sets.add(probe_set)
                print(f"Saving valid {'supplemented ' if is_supplemented else ''}{attribute} probe set #{len(probe_sets)}.")
                if VERBOSE:
                    print(f"  {probe_set}")
                if is_supplemented:
                    supplemented_set_count += 1
                if len(probe_sets) == NUM_SETS:
                    break

    return probe_sets, duplicate_set_count, correlated_set_count, supplemented_set_count


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
Construct N probe sets of 32 probes (8 probes per attribute) based on Latin square selection.
Displays the probe set info to stdout and outputs it to a csv file as input to a future ingest script.
"""
def main(attribute: str):
    attributes = [attribute] if attribute else ATTRIBUTES  # Make a set of attribute(s)
    print(f"Generating {NUM_SETS} uncorrelated probe sets for RQ2 for {attributes}.")

    bucket_data = {}
    # Load medical and attribute delta bucket data
    print(f"Reading medical and attribute delta bucket information from {BUCKET_FILENAME}.")
    try:
        excel_data = import_buckets(BUCKET_FILENAME)
        for acronym, bucket in excel_data.items():
            bucket_data[acronym] = [bucket['medical_deltas'], bucket['attribute_deltas']]
            if VERBOSE:
                print(f"Attribute acronym: {acronym}")
                print("Medical Deltas:", bucket_data[acronym][0])
                print("Attribute Deltas:", bucket_data[acronym][1])
                print()
    except Exception as e:
        print(f"An error occurred creating buckets: {e}.  Exiting.")
        exit(1)
    print('Done.')

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
        probe_sets, duplicate_set_count, correlated_set_count, supplemented_set_count = generate_probe_sets(bucket_data, probe_data, attr)

        # Output the probe sets
        print()
        print(f"Displaying {NUM_SETS} uncorrelated {PROBES_PER_SET}-probe {attr} probe sets:")
        for i, probe_set in enumerate(probe_sets):
            print(f"  Set{i+1}: " + ", ".join(map(str, probe_set)))

        print(f"Total duplicate sets: {duplicate_set_count}")
        print(f"Total correlated sets: {correlated_set_count}")
        print(f"Total supplemented sets: {supplemented_set_count}")

        # Add attribute probe sets to the master list of probe sets
        attr_probe_sets = [[probe_id for probe_id in probe_set] for probe_set in probe_sets]
        all_probe_sets.append({'attribute': attr, 'probe_sets': attr_probe_sets})

    print()
    print(f"Recombining attribute probe sets into master list of {NUM_SETS} probe sets.")
    # Save all probe sets to a CSV file, if requested
    if WRITE_FILES:
        save_probe_sets_to_csv(all_probe_sets, OUTPUT_CSV_FILENAME)
        print(f"Saving RQ2 probe sets to {OUTPUT_CSV_FILENAME}")

    print("Done!")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate RQ2 probe sets')
    parser.add_argument('-n', '--numsets', type=int, required=False, default=NUM_SETS,
                        help=f"Number of sets (default {NUM_SETS})")
    parser.add_argument('-a', '--attribute', required=False, default=None,
                        help='Attribute of the probe set to generate (AF, MF, SS, or PS), or all by default')
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
