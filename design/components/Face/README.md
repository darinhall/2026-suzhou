# Face

The robot's eyes: two 7×7 dot-matrix grids — idle, blink, happy, listening/thinking.

- Consumer provides: the state from the protocol (`idle` `blink` `happy` `ok` `listening` `thinking`).
- Lit dots `ink`, unlit `surface-sunk`. Listening/thinking turn the lit dots `lilac` (AI is working).
- Unread: a 10px `accent` dot top-right during `blink`.
- Eyes stay centred; the body does the expressing (nod, turn).
