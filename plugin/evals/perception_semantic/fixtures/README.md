# Semantic perception fixture taxonomy

Organize by **phenomenon**, then app — not by app alone.

```text
fixtures/
├── surface_composition/     # nested / overlay stacks
├── ownership/               # claim → owner_surface
├── selection_state/         # typed selected_count predicates
├── overlays/
├── object_binding/
├── affordances/
├── latent_affordances/
├── cross_surface/           # contamination / distractors / authority
├── partial_observation/
├── sensor_conflict/         # AX vs pixels
├── task_conditioning/       # intention → action frontier
└── transition_verification/
```

Each case JSON carries:

```json
{
  "phenomena": ["nested_surfaces", "cross_surface_selection", "foreground_authority"],
  "app": "WhatsApp"
}
```

so scorecards can answer “foreground ownership across all apps?”
