# Targeted Crime Detection (Crime Targets)

The **Crime Target** feature allows you to narrow the focus of the AI sentinel to specific types of anomalies. Instead of alerting on any suspicious activity, the system will prioritize and filter for the specific crime category you define.

---

## 1. How to Use
You can specify a target using the `--crime_target` flag when running the scanner.

### Examples:
**Monitor specifically for shoplifting or theft:**
```bash
python run_realtime.py --mode fast --crime_target stealing --video_path /path/to/video.mp4
```

**Monitor specifically for fires or arson:**
```bash
python run_realtime.py --mode high_accuracy --crime_target fire --input_type rtsp --input_source rtsp://camera_url
```

---

## 2. Supported Targets
The system currently supports the following targets and their aliases:

| Target Key | Aliases | Focus Area |
| :--- | :--- | :--- |
| `all` | (default) | Any suspicious or harmful event |
| `stealing` | theft, shoplifting | Theft, burglary, snatching, looting |
| `assault` | fight, violence | Physical confrontations, brawls, attacks |
| `fire` | arson, smoke | Flames, ignition, burning, smoke detection |
| `intrusion` | trespassing, break-in | Unauthorized entry, forced entry |
| `accident` | crash, collision, fall | Vehicle accidents, slips, medical distress |
| `vandalism` | damage, graffiti | Property destruction, smashing objects |
| `robbery` | robber | Armed theft, theft with force/threat |

---

## 3. How It Works Internally
The system uses a three-layer approach to ensure target accuracy:

### Layer 1: Dynamic Prompting
When a target like `assault` is selected, the system modifies the prompt sent to the Vision Language Model (Qwen2-VL):
- **Base Prompt**: "Is there any sign of a suspicious event?"
- **Targeted Prompt**: "ONLY this target crime: **assault, fight, or physical confrontation**. Ignore unrelated events."

### Layer 2: Keyword Filtering
After the AI generates a description of the event, the system checks the text against a list of pre-defined keywords for that profile.
- *Example*: If the target is `fire` and the AI describes "a person running," the system will double-check if "fire" or "smoke" is mentioned. If not, the alert is suppressed.

### Layer 3: Event Tagging
In `high_accuracy` mode, the AI is required to output JSON tags. The system compares these tags against the allowed tags for the profile.
- *Example*: The `stealing` profile only allows tags like `theft`, `intrusion`, or `other`. If the AI tags an event as `violence`, it is filtered out from a `stealing` run.

---

## 4. Benefits of Using Targets
1. **Reduced False Positives**: By telling the AI what to ignore, you reduce alerts from benign but "busy" activities (like people running to catch a bus when you only care about theft).
2. **Reduced Alert Fatigue**: Security supervisors only see alerts relevant to their current priority.
3. **Improved Accuracy**: The VLM performs better when it has a specific "mission" rather than a general monitoring task.

---

## 5. Adding New Targets
New targets can be added by modifying the `CRIME_PROFILES` dictionary in `configs.py`. Each profile requires:
- `display_name`: How it appears in logs.
- `prompt_focus`: The specific words used to guide the AI.
- `keywords`: A list of words used to verify the AI's description.
- `event_tags`: The allowed JSON tags for that category.
