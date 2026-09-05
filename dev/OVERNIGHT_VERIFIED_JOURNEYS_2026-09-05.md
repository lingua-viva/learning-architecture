# Teacher journeys checked during the overnight build

These checks used synthetic learners and documents in an isolated workspace.
They are automated evidence, not a teacher witness or a claim that every UX is
level 4. Claudia's real pagella retry has not started.

## Assess: work sample to a saved diagnostic

1. Open **Assess** and choose the student.
2. Type a sample, choose a document/photo/recording, or record with the microphone.
3. Read and correct the resulting text. Confirm it before analysing.
4. Review each of the four findings and its quoted evidence. Edit suggestions and
   explicitly confirm them. The result has no grade or automatic CEFR change.
5. Save the diagnostic. It appears in the lens and as a printable version in
   **Sources**. Sources also reopens unfinished correction/review checkpoints and
   downloads originals. Continuing an earlier draft creates a new revision.
6. Removing a diagnostic from the active lens preserves its historical record.

Checked: text, a typeset Italian photo, scanned PDF, English and Italian synthetic
speech, and the app's recording control. Real handwriting, child speech and
classroom noise still need teacher checks; text correction is mandatory.

## Observe: dictated note to lens and retained audio

Choose the student in **Observe**, dictate, correct the words, then save the
observation. **Sources** reopens the saved words and downloads the original audio.
Changing students clears the draft and its recording links. Restricted content
goes to the restricted local workflow, not normal saved work.

## Prepare: coursework to classroom packet

Upload the lesson file in **Prepare**, confirm the topic, and choose **Generate
Activity**. Review the three tiers before **Preview Printable Packet**, then
**Save Packet**. The packet reopens in **Sources** with print controls.

The browser check used an uploaded water-cycle lesson and the actual local
model. Each tier visibly contained evaporation, condensation or precipitation.
The test checked saving and reopening; a physical printer was not exercised.

## Summaries: reviewed parent note

Choose the student in **Summaries**, draft the note, review the statements and
approve. The approved revision reopens, downloads and prints from **Sources**.
Explicitly reviewed active assessment findings can inform the note. Withdrawing
the assessment removes those findings from subsequent notes, preserving earlier
approved versions.

## Administrator: question to saved answer

Switch to the coordinator role, open **Lens queries**, choose a question and
complete its parameters. Run and save the answer, then download its CSV. The
saved answer also appears in **Sources**.

## Preservation and scope

The application can be replaced while the workspace remains on disk. Default
locations are `~/.lingua-viva/vault/sources` for retained originals,
`~/.lingua-viva/imports` for import runs, the existing student SQLite store under
`~/.lingua-viva/runtime`, and `~/.lingua-viva/deliverables/saved` for saved work.
An explicitly configured workspace root takes precedence.

Home, Daily, Plan and Slack are absent from navigation in both school profiles.
This document does not certify the remaining unlisted journeys. English and
Italian restricted-document route tests passed; a native-speaker safeguarding
review, Claudia's real import chain and a clean-Mac teacher run remain pending.

Release, installer and preservation measurements are recorded in
[the build diary](OVERNIGHT_BUILD_2026-09-05.md).
