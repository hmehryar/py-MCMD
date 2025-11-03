import pandas as pd

def parse_gomc_log(log_lines, box_number, current_step=0):
    """Extract GOMC energy and box statistics into a DataFrame."""

    e_titles, e_values = None, []
    s_titles, s_values = None, []

    get_e_titles = True
    get_s_titles = True

    for i, line in enumerate(log_lines):
        if line.startswith("ETITLE:") and get_e_titles:
            e_titles = line.split()
            get_e_titles = False

        elif line.startswith(f"ENER_{box_number}:"):
            values = line.split()
            parsed = []
            for j, val in enumerate(values):
                key = e_titles[j]
                if key == "ETITLE:":
                    parsed.append(val)
                elif key == "STEP":
                    parsed.append(int(val) + current_step)
                else:
                    parsed.append(float(val))  
            e_values.append(parsed)

        elif line.startswith("STITLE:") and get_s_titles:
            s_titles = line.split()
            get_s_titles = False

        elif line.startswith(f"STAT_{box_number}:"):
            values = line.split()
            parsed = []
            for j, val in enumerate(values):
                key = s_titles[j]
                if key == "STITLE:":
                    parsed.append(val)
                elif key == "STEP":
                    parsed.append(int(val) + current_step)
                else:
                    parsed.append(float(val))
            s_values.append(parsed)

    if not e_values or e_titles is None:
        raise ValueError("No energy data found in GOMC log.")

    df = pd.DataFrame(e_values, columns=e_titles)
    return df
