# Opisy scenariuszy benchmarkowych

Poniżej znajduje się krótka charakterystyka scen, aby ułatwić interpretację metryk z benchmarku.

## reflections_regal_plamka

- Typ trudności: refleksy i wielokrotne punkty o wysokiej jasności.
- Oczekiwane zachowanie: niska liczba `false_detections_per_frame` i mało przełączeń `track_id`.

## flicker_sledzenie_plamki

- Typ trudności: migotanie jasności i niestabilny próg segmentacji.
- Oczekiwane zachowanie: długi `stable_track_len_frames` oraz umiarkowany udział predykcji Kalmana.

## dynamic_bg_luca_regal

- Typ trudności: dynamiczne tło oraz obiekty konkurujące z celem.
- Oczekiwane zachowanie: niski `track_id_switches` przy możliwie wysokim `stable_track_len_frames`.
