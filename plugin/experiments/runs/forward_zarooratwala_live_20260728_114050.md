# Run log — `wa-forward-live-1785219051`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260728_114050.jsonl`
- Events: 2686

| seq | status | kind | detail |
|----:|:------:|------|--------|
| 1 | ok | whatsapp_forward_message | find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 2 | ok | step | checking Terminal Accessibility |
| 3 | ok | check | pass |
| 4 | ok | check | pass |
| 5 | fail | check | fail |
| 6 | ok | check | pass |
| 7 | ok | step | launched via open -a |
| 8 | ok | step | WhatsApp startup settle |
| 9 | ok | step | app=WhatsApp screenshot=True |
| 10 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 11 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 12 | ok | observation |  |
| 13 | ok | world_patch | dialog |
| 14 | ok | step | attempt 1: leaving open='dialog' toward chat list |
| 15 | ok | step | after preclear list |
| 16 | ok | step | app=WhatsApp screenshot=True |
| 17 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 18 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 19 | ok | observation |  |
| 20 | ok | world_patch | dialog |
| 21 | ok | step | attempt 2: leaving open='storage_warning_dialog' toward chat list |
| 22 | ok | step | after preclear list |
| 23 | ok | step | app=WhatsApp screenshot=True |
| 24 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 25 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 26 | ok | observation |  |
| 27 | ok | world_patch | dialog |
| 28 | ok | step | closed-loop goal=find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 29 | ok | loop_budget |  |
| 30 | ok | step | app=WhatsApp screenshot=True |
| 31 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 32 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 33 | ok | observation |  |
| 34 | ok | observation |  |
| 35 | ok | storage_cleanup |  |
| 36 | ok | step | storage pressure cleanup |
| 37 | ok | step | app=WhatsApp screenshot=True |
| 38 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 39 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 40 | ok | observation |  |
| 41 | ok | observation |  |
| 42 | ok | forward_task |  |
| 43 | ok | world_patch | dialog |
| 44 | ok | fusion_conflicts |  |
| 45 | ok | goal_status |  |
| 46 | ok | decision_engine |  |
| 47 | ok | planner_decision |  |
| 48 | ok | execution | pressed Escape |
| 49 | ok | step | transition settle |
| 50 | ok | step | app=WhatsApp screenshot=True |
| 51 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 52 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 53 | ok | observation |  |
| 54 | ok | step | transition poll |
| 55 | ok | perception_retry |  |
| 56 | ok | step | perception retry (fusion_agreement_low) |
| 57 | ok | step | app=WhatsApp screenshot=True |
| 58 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 59 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 60 | ok | observation |  |
| 61 | fail | perception_unsettled |  |
| 62 | ok | post_observation |  |
| 63 | ok | post_world_patch |  |
| 64 | fail | transition_eval |  |
| 65 | ok | transition_attribution |  |
| 66 | fail | verification |  |
| 67 | ok | step | app=WhatsApp screenshot=True |
| 68 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 69 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 70 | ok | observation |  |
| 71 | ok | post_transition_richer_reobserve |  |
| 72 | fail | forward_predicate_rollback |  |
| 73 | ok | step | app=WhatsApp screenshot=True |
| 74 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 75 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 76 | ok | observation |  |
| 77 | ok | observation |  |
| 78 | ok | forward_task |  |
| 79 | ok | world_patch | dialog |
| 80 | ok | fusion_conflicts |  |
| 81 | ok | goal_status |  |
| 82 | ok | decision_engine |  |
| 83 | ok | planner_decision |  |
| 84 | ok | execution | pressed Escape |
| 85 | ok | step | transition settle |
| 86 | ok | step | app=WhatsApp screenshot=True |
| 87 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 88 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 89 | ok | observation |  |
| 90 | ok | step | transition poll |
| 91 | ok | perception_retry |  |
| 92 | ok | step | perception retry (fusion_agreement_low) |
| 93 | ok | step | app=WhatsApp screenshot=True |
| 94 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 95 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 96 | ok | observation |  |
| 97 | fail | perception_unsettled |  |
| 98 | ok | post_observation |  |
| 99 | ok | post_world_patch |  |
| 100 | fail | transition_eval |  |
| 101 | ok | transition_attribution |  |
| 102 | fail | verification |  |
| 103 | ok | step | app=WhatsApp screenshot=True |
| 104 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 105 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 106 | ok | observation |  |
| 107 | ok | post_transition_richer_reobserve |  |
| 108 | fail | forward_predicate_rollback |  |
| 109 | ok | step | app=WhatsApp screenshot=True |
| 110 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 111 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 112 | ok | observation |  |
| 113 | ok | observation |  |
| 114 | ok | forward_task |  |
| 115 | ok | world_patch | dialog |
| 116 | ok | fusion_conflicts |  |
| 117 | ok | goal_status |  |
| 118 | ok | decision_engine |  |
| 119 | ok | planner_decision |  |
| 120 | ok | execution | pressed Escape |
| 121 | ok | step | transition settle |
| 122 | ok | step | app=WhatsApp screenshot=True |
| 123 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 124 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 125 | ok | observation |  |
| 126 | ok | step | transition poll |
| 127 | ok | step | app=WhatsApp screenshot=True |
| 128 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 129 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 130 | ok | observation |  |
| 131 | ok | step | transition poll |
| 132 | ok | perception_retry |  |
| 133 | ok | step | perception retry (fusion_agreement_low) |
| 134 | ok | step | app=WhatsApp screenshot=True |
| 135 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 136 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 137 | ok | observation |  |
| 138 | fail | perception_unsettled |  |
| 139 | ok | post_observation |  |
| 140 | ok | post_world_patch |  |
| 141 | fail | transition_eval |  |
| 142 | ok | transition_attribution |  |
| 143 | fail | verification |  |
| 144 | ok | step | app=WhatsApp screenshot=True |
| 145 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 146 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 147 | ok | observation |  |
| 148 | ok | post_transition_richer_reobserve |  |
| 149 | fail | forward_predicate_rollback |  |
| 150 | ok | step | app=WhatsApp screenshot=True |
| 151 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 152 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 153 | ok | observation |  |
| 154 | ok | observation |  |
| 155 | ok | storage_cleanup |  |
| 156 | ok | step | storage pressure cleanup |
| 157 | ok | step | app=WhatsApp screenshot=True |
| 158 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 159 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 160 | ok | observation |  |
| 161 | ok | observation |  |
| 162 | ok | storage_cleanup |  |
| 163 | ok | step | storage pressure cleanup |
| 164 | ok | step | app=WhatsApp screenshot=True |
| 165 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 166 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 167 | ok | observation |  |
| 168 | ok | observation |  |
| 169 | ok | forward_task |  |
| 170 | ok | world_patch | dialog |
| 171 | ok | fusion_conflicts |  |
| 172 | ok | goal_status |  |
| 173 | ok | decision_engine |  |
| 174 | ok | planner_decision |  |
| 175 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 176 | ok | step | transition settle |
| 177 | ok | step | app=WhatsApp screenshot=True |
| 178 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 179 | ok | step | fallback=pyobjc_ax |
| 180 | ok | step | nodes=1 elapsed=0.00s |
| 181 | ok | observation |  |
| 182 | ok | step | transition poll |
| 183 | ok | step | app=WhatsApp screenshot=True |
| 184 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 185 | ok | step | fallback=pyobjc_ax |
| 186 | ok | step | nodes=1 elapsed=0.00s |
| 187 | ok | observation |  |
| 188 | ok | step | transition poll |
| 189 | ok | step | app=WhatsApp screenshot=True |
| 190 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 191 | ok | step | fallback=pyobjc_ax |
| 192 | ok | step | nodes=1 elapsed=0.00s |
| 193 | ok | observation |  |
| 194 | ok | step | transition poll |
| 195 | ok | step | app=WhatsApp screenshot=True |
| 196 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 197 | ok | step | fallback=pyobjc_ax |
| 198 | ok | step | nodes=1 elapsed=0.00s |
| 199 | ok | observation |  |
| 200 | ok | step | transition poll |
| 201 | ok | perception_retry |  |
| 202 | ok | step | perception retry (fusion_agreement_low) |
| 203 | ok | step | app=WhatsApp screenshot=True |
| 204 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 205 | ok | step | fallback=pyobjc_ax |
| 206 | ok | step | nodes=1 elapsed=0.00s |
| 207 | ok | observation |  |
| 208 | fail | perception_unsettled |  |
| 209 | ok | post_observation |  |
| 210 | ok | post_world_patch |  |
| 211 | fail | transition_eval |  |
| 212 | ok | transition_attribution |  |
| 213 | fail | verification |  |
| 214 | ok | step | app=WhatsApp screenshot=True |
| 215 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 216 | ok | step | fallback=pyobjc_ax |
| 217 | ok | step | nodes=1 elapsed=0.00s |
| 218 | ok | observation |  |
| 219 | ok | post_transition_richer_reobserve |  |
| 220 | fail | forward_predicate_rollback |  |
| 221 | ok | step | app=WhatsApp screenshot=True |
| 222 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 223 | ok | step | fallback=pyobjc_ax |
| 224 | ok | step | nodes=1 elapsed=0.00s |
| 225 | ok | observation |  |
| 226 | ok | observation |  |
| 227 | ok | forward_task |  |
| 228 | ok | world_patch | dialog |
| 229 | ok | goal_status |  |
| 230 | ok | decision_engine |  |
| 231 | ok | planner_decision |  |
| 232 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 233 | ok | step | app=WhatsApp screenshot=True |
| 234 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 235 | ok | step | fallback=pyobjc_ax |
| 236 | ok | step | nodes=1 elapsed=0.00s |
| 237 | ok | observation |  |
| 238 | ok | observation |  |
| 239 | ok | forward_task |  |
| 240 | ok | world_patch | dialog |
| 241 | ok | goal_status |  |
| 242 | ok | decision_engine |  |
| 243 | ok | planner_decision |  |
| 244 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 245 | ok | step | app=WhatsApp screenshot=True |
| 246 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 247 | ok | step | fallback=pyobjc_ax |
| 248 | ok | step | nodes=1 elapsed=0.00s |
| 249 | ok | observation |  |
| 250 | ok | observation |  |
| 251 | ok | forward_task |  |
| 252 | ok | world_patch | dialog |
| 253 | ok | goal_status |  |
| 254 | ok | decision_engine |  |
| 255 | ok | planner_decision |  |
| 256 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 257 | ok | step | transition settle |
| 258 | ok | step | app=WhatsApp screenshot=True |
| 259 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 260 | ok | step | fallback=pyobjc_ax |
| 261 | ok | step | nodes=1 elapsed=0.00s |
| 262 | ok | observation |  |
| 263 | ok | step | transition poll |
| 264 | ok | step | app=WhatsApp screenshot=True |
| 265 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 266 | ok | step | fallback=pyobjc_ax |
| 267 | ok | step | nodes=1 elapsed=0.00s |
| 268 | ok | observation |  |
| 269 | ok | step | transition poll |
| 270 | ok | step | app=WhatsApp screenshot=True |
| 271 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 272 | ok | step | fallback=pyobjc_ax |
| 273 | ok | step | nodes=1 elapsed=0.00s |
| 274 | ok | observation |  |
| 275 | ok | step | transition poll |
| 276 | ok | perception_retry |  |
| 277 | ok | step | perception retry (fusion_agreement_low) |
| 278 | ok | step | app=WhatsApp screenshot=True |
| 279 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 280 | ok | step | fallback=pyobjc_ax |
| 281 | ok | step | nodes=1 elapsed=0.00s |
| 282 | ok | observation |  |
| 283 | fail | perception_unsettled |  |
| 284 | ok | post_observation |  |
| 285 | ok | post_world_patch |  |
| 286 | fail | transition_eval |  |
| 287 | ok | transition_attribution |  |
| 288 | fail | verification |  |
| 289 | ok | step | app=WhatsApp screenshot=True |
| 290 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 291 | ok | step | fallback=pyobjc_ax |
| 292 | ok | step | nodes=1 elapsed=0.00s |
| 293 | ok | observation |  |
| 294 | ok | post_transition_richer_reobserve |  |
| 295 | fail | forward_predicate_rollback |  |
| 296 | ok | step | app=WhatsApp screenshot=True |
| 297 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 298 | ok | step | fallback=pyobjc_ax |
| 299 | ok | step | nodes=1 elapsed=0.00s |
| 300 | ok | observation |  |
| 301 | ok | observation |  |
| 302 | ok | forward_task |  |
| 303 | ok | world_patch | dialog |
| 304 | ok | goal_status |  |
| 305 | ok | decision_engine |  |
| 306 | ok | planner_decision |  |
| 307 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 308 | ok | step | app=WhatsApp screenshot=True |
| 309 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 310 | ok | step | fallback=pyobjc_ax |
| 311 | ok | step | nodes=1 elapsed=0.00s |
| 312 | ok | observation |  |
| 313 | ok | observation |  |
| 314 | ok | forward_task |  |
| 315 | ok | world_patch | dialog |
| 316 | ok | goal_status |  |
| 317 | ok | decision_engine |  |
| 318 | ok | planner_decision |  |
| 319 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 320 | ok | step | app=WhatsApp screenshot=True |
| 321 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 322 | ok | step | fallback=pyobjc_ax |
| 323 | ok | step | nodes=1 elapsed=0.00s |
| 324 | ok | observation |  |
| 325 | ok | observation |  |
| 326 | ok | forward_task |  |
| 327 | ok | world_patch | dialog |
| 328 | ok | goal_status |  |
| 329 | ok | decision_engine |  |
| 330 | ok | planner_decision |  |
| 331 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 332 | ok | step | transition settle |
| 333 | ok | step | app=WhatsApp screenshot=True |
| 334 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 335 | ok | step | fallback=pyobjc_ax |
| 336 | ok | step | nodes=1 elapsed=0.00s |
| 337 | ok | observation |  |
| 338 | ok | step | transition poll |
| 339 | ok | step | app=WhatsApp screenshot=True |
| 340 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 341 | ok | step | fallback=pyobjc_ax |
| 342 | ok | step | nodes=1 elapsed=0.00s |
| 343 | ok | observation |  |
| 344 | ok | step | transition poll |
| 345 | ok | step | app=WhatsApp screenshot=True |
| 346 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 347 | ok | step | fallback=pyobjc_ax |
| 348 | ok | step | nodes=1 elapsed=0.00s |
| 349 | ok | observation |  |
| 350 | ok | step | transition poll |
| 351 | ok | step | app=WhatsApp screenshot=True |
| 352 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 353 | ok | step | fallback=pyobjc_ax |
| 354 | ok | step | nodes=1 elapsed=0.00s |
| 355 | ok | observation |  |
| 356 | ok | step | transition poll |
| 357 | ok | perception_retry |  |
| 358 | ok | step | perception retry (fusion_agreement_low) |
| 359 | ok | step | app=WhatsApp screenshot=True |
| 360 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 361 | ok | step | fallback=pyobjc_ax |
| 362 | ok | step | nodes=1 elapsed=0.00s |
| 363 | ok | observation |  |
| 364 | fail | perception_unsettled |  |
| 365 | ok | post_observation |  |
| 366 | ok | post_world_patch |  |
| 367 | fail | transition_eval |  |
| 368 | ok | transition_attribution |  |
| 369 | fail | verification |  |
| 370 | ok | step | app=WhatsApp screenshot=True |
| 371 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 372 | ok | step | fallback=pyobjc_ax |
| 373 | ok | step | nodes=1 elapsed=0.00s |
| 374 | ok | observation |  |
| 375 | ok | post_transition_richer_reobserve |  |
| 376 | fail | forward_predicate_rollback |  |
| 377 | ok | step | app=WhatsApp screenshot=True |
| 378 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 379 | ok | step | fallback=pyobjc_ax |
| 380 | ok | step | nodes=1 elapsed=0.00s |
| 381 | ok | observation |  |
| 382 | ok | observation |  |
| 383 | ok | forward_task |  |
| 384 | ok | world_patch | dialog |
| 385 | ok | goal_status |  |
| 386 | ok | decision_engine |  |
| 387 | ok | planner_decision |  |
| 388 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 389 | ok | step | app=WhatsApp screenshot=True |
| 390 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 391 | ok | step | fallback=pyobjc_ax |
| 392 | ok | step | nodes=1 elapsed=0.00s |
| 393 | ok | observation |  |
| 394 | ok | observation |  |
| 395 | ok | forward_task |  |
| 396 | ok | world_patch | dialog |
| 397 | ok | goal_status |  |
| 398 | ok | decision_engine |  |
| 399 | ok | planner_decision |  |
| 400 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 401 | ok | step | app=WhatsApp screenshot=True |
| 402 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 403 | ok | step | fallback=pyobjc_ax |
| 404 | ok | step | nodes=1 elapsed=0.00s |
| 405 | ok | observation |  |
| 406 | ok | observation |  |
| 407 | ok | forward_task |  |
| 408 | ok | world_patch | dialog |
| 409 | ok | goal_status |  |
| 410 | ok | decision_engine |  |
| 411 | ok | planner_decision |  |
| 412 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 413 | ok | step | transition settle |
| 414 | ok | step | app=WhatsApp screenshot=True |
| 415 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 416 | ok | step | fallback=pyobjc_ax |
| 417 | ok | step | nodes=1 elapsed=0.00s |
| 418 | ok | observation |  |
| 419 | ok | step | transition poll |
| 420 | ok | step | app=WhatsApp screenshot=True |
| 421 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 422 | ok | step | fallback=pyobjc_ax |
| 423 | ok | step | nodes=1 elapsed=0.00s |
| 424 | ok | observation |  |
| 425 | ok | step | transition poll |
| 426 | ok | step | app=WhatsApp screenshot=True |
| 427 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 428 | ok | step | fallback=pyobjc_ax |
| 429 | ok | step | nodes=1 elapsed=0.00s |
| 430 | ok | observation |  |
| 431 | ok | step | transition poll |
| 432 | ok | perception_retry |  |
| 433 | ok | step | perception retry (fusion_agreement_low) |
| 434 | ok | step | app=WhatsApp screenshot=True |
| 435 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 436 | ok | step | fallback=pyobjc_ax |
| 437 | ok | step | nodes=1 elapsed=0.00s |
| 438 | ok | observation |  |
| 439 | fail | perception_unsettled |  |
| 440 | ok | post_observation |  |
| 441 | ok | post_world_patch |  |
| 442 | fail | transition_eval |  |
| 443 | ok | transition_attribution |  |
| 444 | fail | verification |  |
| 445 | ok | step | app=WhatsApp screenshot=True |
| 446 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 447 | ok | step | fallback=pyobjc_ax |
| 448 | ok | step | nodes=1 elapsed=0.00s |
| 449 | ok | observation |  |
| 450 | ok | post_transition_richer_reobserve |  |
| 451 | fail | forward_predicate_rollback |  |
| 452 | ok | step | app=WhatsApp screenshot=True |
| 453 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 454 | ok | step | fallback=pyobjc_ax |
| 455 | ok | step | nodes=1 elapsed=0.00s |
| 456 | ok | observation |  |
| 457 | ok | observation |  |
| 458 | ok | forward_task |  |
| 459 | ok | world_patch | dialog |
| 460 | ok | goal_status |  |
| 461 | ok | decision_engine |  |
| 462 | ok | planner_decision |  |
| 463 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 464 | ok | step | app=WhatsApp screenshot=True |
| 465 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 466 | ok | step | fallback=pyobjc_ax |
| 467 | ok | step | nodes=1 elapsed=0.00s |
| 468 | ok | observation |  |
| 469 | ok | observation |  |
| 470 | ok | forward_task |  |
| 471 | ok | world_patch | dialog |
| 472 | ok | goal_status |  |
| 473 | ok | decision_engine |  |
| 474 | ok | planner_decision |  |
| 475 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 476 | ok | step | app=WhatsApp screenshot=True |
| 477 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 478 | ok | step | fallback=pyobjc_ax |
| 479 | ok | step | nodes=1 elapsed=0.00s |
| 480 | ok | observation |  |
| 481 | ok | observation |  |
| 482 | ok | forward_task |  |
| 483 | ok | world_patch | dialog |
| 484 | ok | goal_status |  |
| 485 | ok | decision_engine |  |
| 486 | ok | planner_decision |  |
| 487 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 488 | ok | step | transition settle |
| 489 | ok | step | app=WhatsApp screenshot=True |
| 490 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 491 | ok | step | fallback=pyobjc_ax |
| 492 | ok | step | nodes=1 elapsed=0.00s |
| 493 | ok | observation |  |
| 494 | ok | step | transition poll |
| 495 | ok | step | app=WhatsApp screenshot=True |
| 496 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 497 | ok | step | fallback=pyobjc_ax |
| 498 | ok | step | nodes=1 elapsed=0.00s |
| 499 | ok | observation |  |
| 500 | ok | step | transition poll |
| 501 | ok | step | app=WhatsApp screenshot=True |
| 502 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 503 | ok | step | fallback=pyobjc_ax |
| 504 | ok | step | nodes=1 elapsed=0.00s |
| 505 | ok | observation |  |
| 506 | ok | step | transition poll |
| 507 | ok | perception_retry |  |
| 508 | ok | step | perception retry (fusion_agreement_low) |
| 509 | ok | step | app=WhatsApp screenshot=True |
| 510 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 511 | ok | step | fallback=pyobjc_ax |
| 512 | ok | step | nodes=1 elapsed=0.00s |
| 513 | ok | observation |  |
| 514 | fail | perception_unsettled |  |
| 515 | ok | post_observation |  |
| 516 | ok | post_world_patch |  |
| 517 | fail | transition_eval |  |
| 518 | ok | transition_attribution |  |
| 519 | fail | verification |  |
| 520 | ok | step | app=WhatsApp screenshot=True |
| 521 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 522 | ok | step | fallback=pyobjc_ax |
| 523 | ok | step | nodes=1 elapsed=0.00s |
| 524 | ok | observation |  |
| 525 | ok | post_transition_richer_reobserve |  |
| 526 | fail | forward_predicate_rollback |  |
| 527 | ok | step | app=WhatsApp screenshot=True |
| 528 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 529 | ok | step | fallback=pyobjc_ax |
| 530 | ok | step | nodes=1 elapsed=0.00s |
| 531 | ok | observation |  |
| 532 | ok | observation |  |
| 533 | ok | forward_task |  |
| 534 | ok | world_patch | dialog |
| 535 | ok | goal_status |  |
| 536 | ok | decision_engine |  |
| 537 | ok | planner_decision |  |
| 538 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 539 | ok | step | app=WhatsApp screenshot=True |
| 540 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 541 | ok | step | fallback=pyobjc_ax |
| 542 | ok | step | nodes=1 elapsed=0.00s |
| 543 | ok | observation |  |
| 544 | ok | observation |  |
| 545 | ok | forward_task |  |
| 546 | ok | world_patch | dialog |
| 547 | ok | goal_status |  |
| 548 | ok | decision_engine |  |
| 549 | ok | planner_decision |  |
| 550 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 551 | ok | step | app=WhatsApp screenshot=True |
| 552 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 553 | ok | step | fallback=pyobjc_ax |
| 554 | ok | step | nodes=1 elapsed=0.00s |
| 555 | ok | observation |  |
| 556 | ok | observation |  |
| 557 | ok | forward_task |  |
| 558 | ok | world_patch | dialog |
| 559 | ok | goal_status |  |
| 560 | ok | decision_engine |  |
| 561 | ok | planner_decision |  |
| 562 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 563 | ok | step | transition settle |
| 564 | ok | step | app=WhatsApp screenshot=True |
| 565 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 566 | ok | step | fallback=pyobjc_ax |
| 567 | ok | step | nodes=1 elapsed=0.00s |
| 568 | ok | observation |  |
| 569 | ok | step | transition poll |
| 570 | ok | step | app=WhatsApp screenshot=True |
| 571 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 572 | ok | step | fallback=pyobjc_ax |
| 573 | ok | step | nodes=1 elapsed=0.00s |
| 574 | ok | observation |  |
| 575 | ok | step | transition poll |
| 576 | ok | step | app=WhatsApp screenshot=True |
| 577 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 578 | ok | step | fallback=pyobjc_ax |
| 579 | ok | step | nodes=1 elapsed=0.00s |
| 580 | ok | observation |  |
| 581 | ok | step | transition poll |
| 582 | ok | step | app=WhatsApp screenshot=True |
| 583 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 584 | ok | step | fallback=pyobjc_ax |
| 585 | ok | step | nodes=1 elapsed=0.00s |
| 586 | ok | observation |  |
| 587 | ok | step | transition poll |
| 588 | ok | perception_retry |  |
| 589 | ok | step | perception retry (fusion_agreement_low) |
| 590 | ok | step | app=WhatsApp screenshot=True |
| 591 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 592 | ok | step | fallback=pyobjc_ax |
| 593 | ok | step | nodes=1 elapsed=0.00s |
| 594 | ok | observation |  |
| 595 | fail | perception_unsettled |  |
| 596 | ok | post_observation |  |
| 597 | ok | post_world_patch |  |
| 598 | fail | transition_eval |  |
| 599 | ok | transition_attribution |  |
| 600 | fail | verification |  |
| 601 | ok | step | app=WhatsApp screenshot=True |
| 602 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 603 | ok | step | fallback=pyobjc_ax |
| 604 | ok | step | nodes=1 elapsed=0.00s |
| 605 | ok | observation |  |
| 606 | ok | post_transition_richer_reobserve |  |
| 607 | fail | forward_predicate_rollback |  |
| 608 | ok | step | app=WhatsApp screenshot=True |
| 609 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 610 | ok | step | fallback=pyobjc_ax |
| 611 | ok | step | nodes=1 elapsed=0.00s |
| 612 | ok | observation |  |
| 613 | ok | observation |  |
| 614 | ok | forward_task |  |
| 615 | ok | world_patch | dialog |
| 616 | ok | goal_status |  |
| 617 | ok | decision_engine |  |
| 618 | ok | planner_decision |  |
| 619 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 620 | ok | step | app=WhatsApp screenshot=True |
| 621 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 622 | ok | step | fallback=pyobjc_ax |
| 623 | ok | step | nodes=1 elapsed=0.00s |
| 624 | ok | observation |  |
| 625 | ok | observation |  |
| 626 | ok | forward_task |  |
| 627 | ok | world_patch | dialog |
| 628 | ok | goal_status |  |
| 629 | ok | decision_engine |  |
| 630 | ok | planner_decision |  |
| 631 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 632 | ok | step | app=WhatsApp screenshot=True |
| 633 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 634 | ok | step | fallback=pyobjc_ax |
| 635 | ok | step | nodes=1 elapsed=0.00s |
| 636 | ok | observation |  |
| 637 | ok | observation |  |
| 638 | ok | forward_task |  |
| 639 | ok | world_patch | dialog |
| 640 | ok | goal_status |  |
| 641 | ok | decision_engine |  |
| 642 | ok | planner_decision |  |
| 643 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 644 | ok | step | transition settle |
| 645 | ok | step | app=WhatsApp screenshot=True |
| 646 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 647 | ok | step | fallback=pyobjc_ax |
| 648 | ok | step | nodes=1 elapsed=0.00s |
| 649 | ok | observation |  |
| 650 | ok | step | transition poll |
| 651 | ok | step | app=WhatsApp screenshot=True |
| 652 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 653 | ok | step | fallback=pyobjc_ax |
| 654 | ok | step | nodes=1 elapsed=0.00s |
| 655 | ok | observation |  |
| 656 | ok | step | transition poll |
| 657 | ok | step | app=WhatsApp screenshot=True |
| 658 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 659 | ok | step | fallback=pyobjc_ax |
| 660 | ok | step | nodes=1 elapsed=0.00s |
| 661 | ok | observation |  |
| 662 | ok | step | transition poll |
| 663 | ok | perception_retry |  |
| 664 | ok | step | perception retry (fusion_agreement_low) |
| 665 | ok | step | app=WhatsApp screenshot=True |
| 666 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 667 | ok | step | fallback=pyobjc_ax |
| 668 | ok | step | nodes=1 elapsed=0.00s |
| 669 | ok | observation |  |
| 670 | fail | perception_unsettled |  |
| 671 | ok | post_observation |  |
| 672 | ok | post_world_patch |  |
| 673 | fail | transition_eval |  |
| 674 | ok | transition_attribution |  |
| 675 | fail | verification |  |
| 676 | ok | step | app=WhatsApp screenshot=True |
| 677 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 678 | ok | step | fallback=pyobjc_ax |
| 679 | ok | step | nodes=1 elapsed=0.00s |
| 680 | ok | observation |  |
| 681 | ok | post_transition_richer_reobserve |  |
| 682 | fail | forward_predicate_rollback |  |
| 683 | ok | step | app=WhatsApp screenshot=True |
| 684 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 685 | ok | step | fallback=pyobjc_ax |
| 686 | ok | step | nodes=1 elapsed=0.00s |
| 687 | ok | observation |  |
| 688 | ok | observation |  |
| 689 | ok | forward_task |  |
| 690 | ok | world_patch | dialog |
| 691 | ok | goal_status |  |
| 692 | ok | decision_engine |  |
| 693 | ok | planner_decision |  |
| 694 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 695 | ok | step | app=WhatsApp screenshot=True |
| 696 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 697 | ok | step | fallback=pyobjc_ax |
| 698 | ok | step | nodes=1 elapsed=0.00s |
| 699 | ok | observation |  |
| 700 | ok | observation |  |
| 701 | ok | forward_task |  |
| 702 | ok | world_patch | dialog |
| 703 | ok | goal_status |  |
| 704 | ok | decision_engine |  |
| 705 | ok | planner_decision |  |
| 706 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 707 | ok | step | app=WhatsApp screenshot=True |
| 708 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 709 | ok | step | fallback=pyobjc_ax |
| 710 | ok | step | nodes=1 elapsed=0.00s |
| 711 | ok | observation |  |
| 712 | ok | observation |  |
| 713 | ok | forward_task |  |
| 714 | ok | world_patch | dialog |
| 715 | ok | goal_status |  |
| 716 | ok | decision_engine |  |
| 717 | ok | planner_decision |  |
| 718 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 719 | ok | step | transition settle |
| 720 | ok | step | app=WhatsApp screenshot=True |
| 721 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 722 | ok | step | fallback=pyobjc_ax |
| 723 | ok | step | nodes=1 elapsed=0.00s |
| 724 | ok | observation |  |
| 725 | ok | step | transition poll |
| 726 | ok | step | app=WhatsApp screenshot=True |
| 727 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 728 | ok | step | fallback=pyobjc_ax |
| 729 | ok | step | nodes=1 elapsed=0.00s |
| 730 | ok | observation |  |
| 731 | ok | step | transition poll |
| 732 | ok | step | app=WhatsApp screenshot=True |
| 733 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 734 | ok | step | fallback=pyobjc_ax |
| 735 | ok | step | nodes=1 elapsed=0.00s |
| 736 | ok | observation |  |
| 737 | ok | step | transition poll |
| 738 | ok | step | app=WhatsApp screenshot=True |
| 739 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 740 | ok | step | fallback=pyobjc_ax |
| 741 | ok | step | nodes=1 elapsed=0.00s |
| 742 | ok | observation |  |
| 743 | ok | step | transition poll |
| 744 | ok | perception_retry |  |
| 745 | ok | step | perception retry (fusion_agreement_low) |
| 746 | ok | step | app=WhatsApp screenshot=True |
| 747 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 748 | ok | step | fallback=pyobjc_ax |
| 749 | ok | step | nodes=1 elapsed=0.00s |
| 750 | ok | observation |  |
| 751 | fail | perception_unsettled |  |
| 752 | ok | post_observation |  |
| 753 | ok | post_world_patch |  |
| 754 | fail | transition_eval |  |
| 755 | ok | transition_attribution |  |
| 756 | fail | verification |  |
| 757 | ok | step | app=WhatsApp screenshot=True |
| 758 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 759 | ok | step | fallback=pyobjc_ax |
| 760 | ok | step | nodes=1 elapsed=0.00s |
| 761 | ok | observation |  |
| 762 | ok | post_transition_richer_reobserve |  |
| 763 | fail | forward_predicate_rollback |  |
| 764 | ok | step | app=WhatsApp screenshot=True |
| 765 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 766 | ok | step | fallback=pyobjc_ax |
| 767 | ok | step | nodes=1 elapsed=0.00s |
| 768 | ok | observation |  |
| 769 | ok | observation |  |
| 770 | ok | forward_task |  |
| 771 | ok | world_patch | dialog |
| 772 | ok | goal_status |  |
| 773 | ok | decision_engine |  |
| 774 | ok | planner_decision |  |
| 775 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 776 | ok | step | app=WhatsApp screenshot=True |
| 777 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 778 | ok | step | fallback=pyobjc_ax |
| 779 | ok | step | nodes=1 elapsed=0.00s |
| 780 | ok | observation |  |
| 781 | ok | observation |  |
| 782 | ok | forward_task |  |
| 783 | ok | world_patch | dialog |
| 784 | ok | goal_status |  |
| 785 | ok | decision_engine |  |
| 786 | ok | planner_decision |  |
| 787 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 788 | ok | step | app=WhatsApp screenshot=True |
| 789 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 790 | ok | step | fallback=pyobjc_ax |
| 791 | ok | step | nodes=1 elapsed=0.00s |
| 792 | ok | observation |  |
| 793 | ok | observation |  |
| 794 | ok | forward_task |  |
| 795 | ok | world_patch | dialog |
| 796 | ok | goal_status |  |
| 797 | ok | decision_engine |  |
| 798 | ok | planner_decision |  |
| 799 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 800 | ok | step | transition settle |
| 801 | ok | step | app=WhatsApp screenshot=True |
| 802 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 803 | ok | step | fallback=pyobjc_ax |
| 804 | ok | step | nodes=1 elapsed=0.00s |
| 805 | ok | observation |  |
| 806 | ok | step | transition poll |
| 807 | ok | step | app=WhatsApp screenshot=True |
| 808 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 809 | ok | step | fallback=pyobjc_ax |
| 810 | ok | step | nodes=1 elapsed=0.00s |
| 811 | ok | observation |  |
| 812 | ok | step | transition poll |
| 813 | ok | step | app=WhatsApp screenshot=True |
| 814 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 815 | ok | step | fallback=pyobjc_ax |
| 816 | ok | step | nodes=1 elapsed=0.00s |
| 817 | ok | observation |  |
| 818 | ok | step | transition poll |
| 819 | ok | step | app=WhatsApp screenshot=True |
| 820 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 821 | ok | step | fallback=pyobjc_ax |
| 822 | ok | step | nodes=1 elapsed=0.00s |
| 823 | ok | observation |  |
| 824 | ok | step | transition poll |
| 825 | ok | perception_retry |  |
| 826 | ok | step | perception retry (fusion_agreement_low) |
| 827 | ok | step | app=WhatsApp screenshot=True |
| 828 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 829 | ok | step | fallback=pyobjc_ax |
| 830 | ok | step | nodes=1 elapsed=0.00s |
| 831 | ok | observation |  |
| 832 | fail | perception_unsettled |  |
| 833 | ok | post_observation |  |
| 834 | ok | post_world_patch |  |
| 835 | fail | transition_eval |  |
| 836 | ok | transition_attribution |  |
| 837 | fail | verification |  |
| 838 | ok | step | app=WhatsApp screenshot=True |
| 839 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 840 | ok | step | fallback=pyobjc_ax |
| 841 | ok | step | nodes=1 elapsed=0.00s |
| 842 | ok | observation |  |
| 843 | ok | post_transition_richer_reobserve |  |
| 844 | fail | forward_predicate_rollback |  |
| 845 | ok | step | app=WhatsApp screenshot=True |
| 846 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 847 | ok | step | fallback=pyobjc_ax |
| 848 | ok | step | nodes=1 elapsed=0.00s |
| 849 | ok | observation |  |
| 850 | ok | observation |  |
| 851 | ok | forward_task |  |
| 852 | ok | world_patch | dialog |
| 853 | ok | goal_status |  |
| 854 | ok | decision_engine |  |
| 855 | ok | planner_decision |  |
| 856 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 857 | ok | step | app=WhatsApp screenshot=True |
| 858 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 859 | ok | step | fallback=pyobjc_ax |
| 860 | ok | step | nodes=1 elapsed=0.00s |
| 861 | ok | observation |  |
| 862 | ok | observation |  |
| 863 | ok | forward_task |  |
| 864 | ok | world_patch | dialog |
| 865 | ok | goal_status |  |
| 866 | ok | decision_engine |  |
| 867 | ok | planner_decision |  |
| 868 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 869 | ok | step | app=WhatsApp screenshot=True |
| 870 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 871 | ok | step | fallback=pyobjc_ax |
| 872 | ok | step | nodes=1 elapsed=0.00s |
| 873 | ok | observation |  |
| 874 | ok | observation |  |
| 875 | ok | forward_task |  |
| 876 | ok | world_patch | dialog |
| 877 | ok | goal_status |  |
| 878 | ok | decision_engine |  |
| 879 | ok | planner_decision |  |
| 880 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 881 | ok | step | transition settle |
| 882 | ok | step | app=WhatsApp screenshot=True |
| 883 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 884 | ok | step | fallback=pyobjc_ax |
| 885 | ok | step | nodes=1 elapsed=0.00s |
| 886 | ok | observation |  |
| 887 | ok | step | transition poll |
| 888 | ok | step | app=WhatsApp screenshot=True |
| 889 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 890 | ok | step | fallback=pyobjc_ax |
| 891 | ok | step | nodes=1 elapsed=0.00s |
| 892 | ok | observation |  |
| 893 | ok | step | transition poll |
| 894 | ok | step | app=WhatsApp screenshot=True |
| 895 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 896 | ok | step | fallback=pyobjc_ax |
| 897 | ok | step | nodes=1 elapsed=0.00s |
| 898 | ok | observation |  |
| 899 | ok | step | transition poll |
| 900 | ok | step | app=WhatsApp screenshot=True |
| 901 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 902 | ok | step | fallback=pyobjc_ax |
| 903 | ok | step | nodes=1 elapsed=0.00s |
| 904 | ok | observation |  |
| 905 | ok | step | transition poll |
| 906 | ok | perception_retry |  |
| 907 | ok | step | perception retry (fusion_agreement_low) |
| 908 | ok | step | app=WhatsApp screenshot=True |
| 909 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 910 | ok | step | fallback=pyobjc_ax |
| 911 | ok | step | nodes=1 elapsed=0.00s |
| 912 | ok | observation |  |
| 913 | fail | perception_unsettled |  |
| 914 | ok | post_observation |  |
| 915 | ok | post_world_patch |  |
| 916 | fail | transition_eval |  |
| 917 | ok | transition_attribution |  |
| 918 | fail | verification |  |
| 919 | ok | step | app=WhatsApp screenshot=True |
| 920 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 921 | ok | step | fallback=pyobjc_ax |
| 922 | ok | step | nodes=1 elapsed=0.00s |
| 923 | ok | observation |  |
| 924 | ok | post_transition_richer_reobserve |  |
| 925 | fail | forward_predicate_rollback |  |
| 926 | ok | step | app=WhatsApp screenshot=True |
| 927 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 928 | ok | step | fallback=pyobjc_ax |
| 929 | ok | step | nodes=1 elapsed=0.00s |
| 930 | ok | observation |  |
| 931 | ok | observation |  |
| 932 | ok | forward_task |  |
| 933 | ok | world_patch | dialog |
| 934 | ok | goal_status |  |
| 935 | ok | decision_engine |  |
| 936 | ok | planner_decision |  |
| 937 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 938 | ok | step | app=WhatsApp screenshot=True |
| 939 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 940 | ok | step | fallback=pyobjc_ax |
| 941 | ok | step | nodes=1 elapsed=0.00s |
| 942 | ok | observation |  |
| 943 | ok | observation |  |
| 944 | ok | forward_task |  |
| 945 | ok | world_patch | dialog |
| 946 | ok | goal_status |  |
| 947 | ok | decision_engine |  |
| 948 | ok | planner_decision |  |
| 949 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 950 | ok | step | app=WhatsApp screenshot=True |
| 951 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 952 | ok | step | fallback=pyobjc_ax |
| 953 | ok | step | nodes=1 elapsed=0.00s |
| 954 | ok | observation |  |
| 955 | ok | observation |  |
| 956 | ok | forward_task |  |
| 957 | ok | world_patch | dialog |
| 958 | ok | goal_status |  |
| 959 | ok | decision_engine |  |
| 960 | ok | planner_decision |  |
| 961 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 962 | ok | step | transition settle |
| 963 | ok | step | app=WhatsApp screenshot=True |
| 964 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 965 | ok | step | fallback=pyobjc_ax |
| 966 | ok | step | nodes=1 elapsed=0.00s |
| 967 | ok | observation |  |
| 968 | ok | step | transition poll |
| 969 | ok | step | app=WhatsApp screenshot=True |
| 970 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 971 | ok | step | fallback=pyobjc_ax |
| 972 | ok | step | nodes=1 elapsed=0.00s |
| 973 | ok | observation |  |
| 974 | ok | step | transition poll |
| 975 | ok | step | app=WhatsApp screenshot=True |
| 976 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 977 | ok | step | fallback=pyobjc_ax |
| 978 | ok | step | nodes=1 elapsed=0.00s |
| 979 | ok | observation |  |
| 980 | ok | step | transition poll |
| 981 | ok | step | app=WhatsApp screenshot=True |
| 982 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 983 | ok | step | fallback=pyobjc_ax |
| 984 | ok | step | nodes=1 elapsed=0.00s |
| 985 | ok | observation |  |
| 986 | ok | step | transition poll |
| 987 | ok | perception_retry |  |
| 988 | ok | step | perception retry (fusion_agreement_low) |
| 989 | ok | step | app=WhatsApp screenshot=True |
| 990 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 991 | ok | step | fallback=pyobjc_ax |
| 992 | ok | step | nodes=1 elapsed=0.00s |
| 993 | ok | observation |  |
| 994 | fail | perception_unsettled |  |
| 995 | ok | post_observation |  |
| 996 | ok | post_world_patch |  |
| 997 | fail | transition_eval |  |
| 998 | ok | transition_attribution |  |
| 999 | fail | verification |  |
| 1000 | ok | step | app=WhatsApp screenshot=True |
| 1001 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1002 | ok | step | fallback=pyobjc_ax |
| 1003 | ok | step | nodes=1 elapsed=0.00s |
| 1004 | ok | observation |  |
| 1005 | ok | post_transition_richer_reobserve |  |
| 1006 | fail | forward_predicate_rollback |  |
| 1007 | ok | step | app=WhatsApp screenshot=True |
| 1008 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1009 | ok | step | fallback=pyobjc_ax |
| 1010 | ok | step | nodes=1 elapsed=0.00s |
| 1011 | ok | observation |  |
| 1012 | ok | observation |  |
| 1013 | ok | forward_task |  |
| 1014 | ok | world_patch | dialog |
| 1015 | ok | goal_status |  |
| 1016 | ok | decision_engine |  |
| 1017 | ok | planner_decision |  |
| 1018 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1019 | ok | step | app=WhatsApp screenshot=True |
| 1020 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1021 | ok | step | fallback=pyobjc_ax |
| 1022 | ok | step | nodes=1 elapsed=0.00s |
| 1023 | ok | observation |  |
| 1024 | ok | observation |  |
| 1025 | ok | forward_task |  |
| 1026 | ok | world_patch | dialog |
| 1027 | ok | goal_status |  |
| 1028 | ok | decision_engine |  |
| 1029 | ok | planner_decision |  |
| 1030 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1031 | ok | step | app=WhatsApp screenshot=True |
| 1032 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1033 | ok | step | fallback=pyobjc_ax |
| 1034 | ok | step | nodes=1 elapsed=0.00s |
| 1035 | ok | observation |  |
| 1036 | ok | observation |  |
| 1037 | ok | forward_task |  |
| 1038 | ok | world_patch | dialog |
| 1039 | ok | goal_status |  |
| 1040 | ok | decision_engine |  |
| 1041 | ok | planner_decision |  |
| 1042 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1043 | ok | step | transition settle |
| 1044 | ok | step | app=WhatsApp screenshot=True |
| 1045 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1046 | ok | step | fallback=pyobjc_ax |
| 1047 | ok | step | nodes=1 elapsed=0.00s |
| 1048 | ok | observation |  |
| 1049 | ok | step | transition poll |
| 1050 | ok | step | app=WhatsApp screenshot=True |
| 1051 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1052 | ok | step | fallback=pyobjc_ax |
| 1053 | ok | step | nodes=1 elapsed=0.00s |
| 1054 | ok | observation |  |
| 1055 | ok | step | transition poll |
| 1056 | ok | step | app=WhatsApp screenshot=True |
| 1057 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1058 | ok | step | fallback=pyobjc_ax |
| 1059 | ok | step | nodes=1 elapsed=0.00s |
| 1060 | ok | observation |  |
| 1061 | ok | step | transition poll |
| 1062 | ok | step | app=WhatsApp screenshot=True |
| 1063 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1064 | ok | step | fallback=pyobjc_ax |
| 1065 | ok | step | nodes=1 elapsed=0.00s |
| 1066 | ok | observation |  |
| 1067 | ok | step | transition poll |
| 1068 | ok | perception_retry |  |
| 1069 | ok | step | perception retry (fusion_agreement_low) |
| 1070 | ok | step | app=WhatsApp screenshot=True |
| 1071 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1072 | ok | step | fallback=pyobjc_ax |
| 1073 | ok | step | nodes=1 elapsed=0.00s |
| 1074 | ok | observation |  |
| 1075 | fail | perception_unsettled |  |
| 1076 | ok | post_observation |  |
| 1077 | ok | post_world_patch |  |
| 1078 | fail | transition_eval |  |
| 1079 | ok | transition_attribution |  |
| 1080 | fail | verification |  |
| 1081 | ok | step | app=WhatsApp screenshot=True |
| 1082 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1083 | ok | step | fallback=pyobjc_ax |
| 1084 | ok | step | nodes=1 elapsed=0.00s |
| 1085 | ok | observation |  |
| 1086 | ok | post_transition_richer_reobserve |  |
| 1087 | fail | forward_predicate_rollback |  |
| 1088 | ok | step | app=WhatsApp screenshot=True |
| 1089 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1090 | ok | step | fallback=pyobjc_ax |
| 1091 | ok | step | nodes=1 elapsed=0.00s |
| 1092 | ok | observation |  |
| 1093 | ok | observation |  |
| 1094 | ok | forward_task |  |
| 1095 | ok | world_patch | dialog |
| 1096 | ok | goal_status |  |
| 1097 | ok | decision_engine |  |
| 1098 | ok | planner_decision |  |
| 1099 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1100 | ok | step | app=WhatsApp screenshot=True |
| 1101 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1102 | ok | step | fallback=pyobjc_ax |
| 1103 | ok | step | nodes=1 elapsed=0.00s |
| 1104 | ok | observation |  |
| 1105 | ok | observation |  |
| 1106 | ok | forward_task |  |
| 1107 | ok | world_patch | dialog |
| 1108 | ok | goal_status |  |
| 1109 | ok | decision_engine |  |
| 1110 | ok | planner_decision |  |
| 1111 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1112 | ok | step | app=WhatsApp screenshot=True |
| 1113 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1114 | ok | step | fallback=pyobjc_ax |
| 1115 | ok | step | nodes=1 elapsed=0.00s |
| 1116 | ok | observation |  |
| 1117 | ok | observation |  |
| 1118 | ok | forward_task |  |
| 1119 | ok | world_patch | dialog |
| 1120 | ok | goal_status |  |
| 1121 | ok | decision_engine |  |
| 1122 | ok | planner_decision |  |
| 1123 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1124 | ok | step | transition settle |
| 1125 | ok | step | app=WhatsApp screenshot=True |
| 1126 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1127 | ok | step | fallback=pyobjc_ax |
| 1128 | ok | step | nodes=1 elapsed=0.00s |
| 1129 | ok | observation |  |
| 1130 | ok | step | transition poll |
| 1131 | ok | step | app=WhatsApp screenshot=True |
| 1132 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1133 | ok | step | fallback=pyobjc_ax |
| 1134 | ok | step | nodes=1 elapsed=0.00s |
| 1135 | ok | observation |  |
| 1136 | ok | step | transition poll |
| 1137 | ok | step | app=WhatsApp screenshot=True |
| 1138 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1139 | ok | step | fallback=pyobjc_ax |
| 1140 | ok | step | nodes=1 elapsed=0.00s |
| 1141 | ok | observation |  |
| 1142 | ok | step | transition poll |
| 1143 | ok | step | app=WhatsApp screenshot=True |
| 1144 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1145 | ok | step | fallback=pyobjc_ax |
| 1146 | ok | step | nodes=1 elapsed=0.00s |
| 1147 | ok | observation |  |
| 1148 | ok | step | transition poll |
| 1149 | ok | perception_retry |  |
| 1150 | ok | step | perception retry (fusion_agreement_low) |
| 1151 | ok | step | app=WhatsApp screenshot=True |
| 1152 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1153 | ok | step | fallback=pyobjc_ax |
| 1154 | ok | step | nodes=1 elapsed=0.00s |
| 1155 | ok | observation |  |
| 1156 | fail | perception_unsettled |  |
| 1157 | ok | post_observation |  |
| 1158 | ok | post_world_patch |  |
| 1159 | fail | transition_eval |  |
| 1160 | ok | transition_attribution |  |
| 1161 | fail | verification |  |
| 1162 | ok | step | app=WhatsApp screenshot=True |
| 1163 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1164 | ok | step | fallback=pyobjc_ax |
| 1165 | ok | step | nodes=1 elapsed=0.00s |
| 1166 | ok | observation |  |
| 1167 | ok | post_transition_richer_reobserve |  |
| 1168 | fail | forward_predicate_rollback |  |
| 1169 | ok | step | app=WhatsApp screenshot=True |
| 1170 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1171 | ok | step | fallback=pyobjc_ax |
| 1172 | ok | step | nodes=1 elapsed=0.00s |
| 1173 | ok | observation |  |
| 1174 | ok | observation |  |
| 1175 | ok | forward_task |  |
| 1176 | ok | world_patch | dialog |
| 1177 | ok | goal_status |  |
| 1178 | ok | decision_engine |  |
| 1179 | ok | planner_decision |  |
| 1180 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1181 | ok | step | app=WhatsApp screenshot=True |
| 1182 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1183 | ok | step | fallback=pyobjc_ax |
| 1184 | ok | step | nodes=1 elapsed=0.00s |
| 1185 | ok | observation |  |
| 1186 | ok | observation |  |
| 1187 | ok | forward_task |  |
| 1188 | ok | world_patch | dialog |
| 1189 | ok | goal_status |  |
| 1190 | ok | decision_engine |  |
| 1191 | ok | planner_decision |  |
| 1192 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1193 | ok | step | app=WhatsApp screenshot=True |
| 1194 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1195 | ok | step | fallback=pyobjc_ax |
| 1196 | ok | step | nodes=1 elapsed=0.00s |
| 1197 | ok | observation |  |
| 1198 | ok | observation |  |
| 1199 | ok | forward_task |  |
| 1200 | ok | world_patch | dialog |
| 1201 | ok | goal_status |  |
| 1202 | ok | decision_engine |  |
| 1203 | ok | planner_decision |  |
| 1204 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1205 | ok | step | transition settle |
| 1206 | ok | step | app=WhatsApp screenshot=True |
| 1207 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1208 | ok | step | fallback=pyobjc_ax |
| 1209 | ok | step | nodes=1 elapsed=0.00s |
| 1210 | ok | observation |  |
| 1211 | ok | step | transition poll |
| 1212 | ok | step | app=WhatsApp screenshot=True |
| 1213 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1214 | ok | step | fallback=pyobjc_ax |
| 1215 | ok | step | nodes=1 elapsed=0.00s |
| 1216 | ok | observation |  |
| 1217 | ok | step | transition poll |
| 1218 | ok | step | app=WhatsApp screenshot=True |
| 1219 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1220 | ok | step | fallback=pyobjc_ax |
| 1221 | ok | step | nodes=1 elapsed=0.00s |
| 1222 | ok | observation |  |
| 1223 | ok | step | transition poll |
| 1224 | ok | step | app=WhatsApp screenshot=True |
| 1225 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1226 | ok | step | fallback=pyobjc_ax |
| 1227 | ok | step | nodes=1 elapsed=0.00s |
| 1228 | ok | observation |  |
| 1229 | ok | step | transition poll |
| 1230 | ok | perception_retry |  |
| 1231 | ok | step | perception retry (fusion_agreement_low) |
| 1232 | ok | step | app=WhatsApp screenshot=True |
| 1233 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1234 | ok | step | fallback=pyobjc_ax |
| 1235 | ok | step | nodes=1 elapsed=0.00s |
| 1236 | ok | observation |  |
| 1237 | fail | perception_unsettled |  |
| 1238 | ok | post_observation |  |
| 1239 | ok | post_world_patch |  |
| 1240 | fail | transition_eval |  |
| 1241 | ok | transition_attribution |  |
| 1242 | fail | verification |  |
| 1243 | ok | step | app=WhatsApp screenshot=True |
| 1244 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1245 | ok | step | fallback=pyobjc_ax |
| 1246 | ok | step | nodes=1 elapsed=0.00s |
| 1247 | ok | observation |  |
| 1248 | ok | post_transition_richer_reobserve |  |
| 1249 | fail | forward_predicate_rollback |  |
| 1250 | ok | step | app=WhatsApp screenshot=True |
| 1251 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1252 | ok | step | fallback=pyobjc_ax |
| 1253 | ok | step | nodes=1 elapsed=0.00s |
| 1254 | ok | observation |  |
| 1255 | ok | observation |  |
| 1256 | ok | forward_task |  |
| 1257 | ok | world_patch | dialog |
| 1258 | ok | goal_status |  |
| 1259 | ok | decision_engine |  |
| 1260 | ok | planner_decision |  |
| 1261 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1262 | ok | step | app=WhatsApp screenshot=True |
| 1263 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1264 | ok | step | fallback=pyobjc_ax |
| 1265 | ok | step | nodes=1 elapsed=0.00s |
| 1266 | ok | observation |  |
| 1267 | ok | observation |  |
| 1268 | ok | forward_task |  |
| 1269 | ok | world_patch | dialog |
| 1270 | ok | goal_status |  |
| 1271 | ok | decision_engine |  |
| 1272 | ok | planner_decision |  |
| 1273 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1274 | ok | step | app=WhatsApp screenshot=True |
| 1275 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1276 | ok | step | fallback=pyobjc_ax |
| 1277 | ok | step | nodes=1 elapsed=0.00s |
| 1278 | ok | observation |  |
| 1279 | ok | observation |  |
| 1280 | ok | forward_task |  |
| 1281 | ok | world_patch | dialog |
| 1282 | ok | goal_status |  |
| 1283 | ok | decision_engine |  |
| 1284 | ok | planner_decision |  |
| 1285 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1286 | ok | step | transition settle |
| 1287 | ok | step | app=WhatsApp screenshot=True |
| 1288 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1289 | ok | step | fallback=pyobjc_ax |
| 1290 | ok | step | nodes=1 elapsed=0.00s |
| 1291 | ok | observation |  |
| 1292 | ok | step | transition poll |
| 1293 | ok | step | app=WhatsApp screenshot=True |
| 1294 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1295 | ok | step | fallback=pyobjc_ax |
| 1296 | ok | step | nodes=1 elapsed=0.00s |
| 1297 | ok | observation |  |
| 1298 | ok | step | transition poll |
| 1299 | ok | step | app=WhatsApp screenshot=True |
| 1300 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1301 | ok | step | fallback=pyobjc_ax |
| 1302 | ok | step | nodes=1 elapsed=0.00s |
| 1303 | ok | observation |  |
| 1304 | ok | step | transition poll |
| 1305 | ok | step | app=WhatsApp screenshot=True |
| 1306 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1307 | ok | step | fallback=pyobjc_ax |
| 1308 | ok | step | nodes=1 elapsed=0.00s |
| 1309 | ok | observation |  |
| 1310 | ok | step | transition poll |
| 1311 | ok | perception_retry |  |
| 1312 | ok | step | perception retry (fusion_agreement_low) |
| 1313 | ok | step | app=WhatsApp screenshot=True |
| 1314 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1315 | ok | step | fallback=pyobjc_ax |
| 1316 | ok | step | nodes=1 elapsed=0.00s |
| 1317 | ok | observation |  |
| 1318 | fail | perception_unsettled |  |
| 1319 | ok | post_observation |  |
| 1320 | ok | post_world_patch |  |
| 1321 | fail | transition_eval |  |
| 1322 | ok | transition_attribution |  |
| 1323 | fail | verification |  |
| 1324 | ok | step | app=WhatsApp screenshot=True |
| 1325 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1326 | ok | step | fallback=pyobjc_ax |
| 1327 | ok | step | nodes=1 elapsed=0.00s |
| 1328 | ok | observation |  |
| 1329 | ok | post_transition_richer_reobserve |  |
| 1330 | fail | forward_predicate_rollback |  |
| 1331 | ok | step | app=WhatsApp screenshot=True |
| 1332 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1333 | ok | step | fallback=pyobjc_ax |
| 1334 | ok | step | nodes=1 elapsed=0.00s |
| 1335 | ok | observation |  |
| 1336 | ok | observation |  |
| 1337 | ok | forward_task |  |
| 1338 | ok | world_patch | dialog |
| 1339 | ok | goal_status |  |
| 1340 | ok | decision_engine |  |
| 1341 | ok | planner_decision |  |
| 1342 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1343 | ok | step | app=WhatsApp screenshot=True |
| 1344 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1345 | ok | step | fallback=pyobjc_ax |
| 1346 | ok | step | nodes=1 elapsed=0.00s |
| 1347 | ok | observation |  |
| 1348 | ok | observation |  |
| 1349 | ok | forward_task |  |
| 1350 | ok | world_patch | dialog |
| 1351 | ok | goal_status |  |
| 1352 | ok | decision_engine |  |
| 1353 | ok | planner_decision |  |
| 1354 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1355 | ok | step | app=WhatsApp screenshot=True |
| 1356 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1357 | ok | step | fallback=pyobjc_ax |
| 1358 | ok | step | nodes=1 elapsed=0.00s |
| 1359 | ok | observation |  |
| 1360 | ok | observation |  |
| 1361 | ok | forward_task |  |
| 1362 | ok | world_patch | dialog |
| 1363 | ok | goal_status |  |
| 1364 | ok | decision_engine |  |
| 1365 | ok | planner_decision |  |
| 1366 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1367 | ok | step | transition settle |
| 1368 | ok | step | app=WhatsApp screenshot=True |
| 1369 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1370 | ok | step | fallback=pyobjc_ax |
| 1371 | ok | step | nodes=1 elapsed=0.00s |
| 1372 | ok | observation |  |
| 1373 | ok | step | transition poll |
| 1374 | ok | step | app=WhatsApp screenshot=True |
| 1375 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1376 | ok | step | fallback=pyobjc_ax |
| 1377 | ok | step | nodes=1 elapsed=0.00s |
| 1378 | ok | observation |  |
| 1379 | ok | step | transition poll |
| 1380 | ok | step | app=WhatsApp screenshot=True |
| 1381 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1382 | ok | step | fallback=pyobjc_ax |
| 1383 | ok | step | nodes=1 elapsed=0.00s |
| 1384 | ok | observation |  |
| 1385 | ok | step | transition poll |
| 1386 | ok | step | app=WhatsApp screenshot=True |
| 1387 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1388 | ok | step | fallback=pyobjc_ax |
| 1389 | ok | step | nodes=1 elapsed=0.00s |
| 1390 | ok | observation |  |
| 1391 | ok | step | transition poll |
| 1392 | ok | perception_retry |  |
| 1393 | ok | step | perception retry (fusion_agreement_low) |
| 1394 | ok | step | app=WhatsApp screenshot=True |
| 1395 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1396 | ok | step | fallback=pyobjc_ax |
| 1397 | ok | step | nodes=1 elapsed=0.00s |
| 1398 | ok | observation |  |
| 1399 | fail | perception_unsettled |  |
| 1400 | ok | post_observation |  |
| 1401 | ok | post_world_patch |  |
| 1402 | fail | transition_eval |  |
| 1403 | ok | transition_attribution |  |
| 1404 | fail | verification |  |
| 1405 | ok | step | app=WhatsApp screenshot=True |
| 1406 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1407 | ok | step | fallback=pyobjc_ax |
| 1408 | ok | step | nodes=1 elapsed=0.00s |
| 1409 | ok | observation |  |
| 1410 | ok | post_transition_richer_reobserve |  |
| 1411 | fail | forward_predicate_rollback |  |
| 1412 | ok | step | app=WhatsApp screenshot=True |
| 1413 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1414 | ok | step | fallback=pyobjc_ax |
| 1415 | ok | step | nodes=1 elapsed=0.00s |
| 1416 | ok | observation |  |
| 1417 | ok | observation |  |
| 1418 | ok | forward_task |  |
| 1419 | ok | world_patch | dialog |
| 1420 | ok | goal_status |  |
| 1421 | ok | decision_engine |  |
| 1422 | ok | planner_decision |  |
| 1423 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1424 | ok | step | app=WhatsApp screenshot=True |
| 1425 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1426 | ok | step | fallback=pyobjc_ax |
| 1427 | ok | step | nodes=1 elapsed=0.00s |
| 1428 | ok | observation |  |
| 1429 | ok | observation |  |
| 1430 | ok | forward_task |  |
| 1431 | ok | world_patch | dialog |
| 1432 | ok | goal_status |  |
| 1433 | ok | decision_engine |  |
| 1434 | ok | planner_decision |  |
| 1435 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1436 | ok | step | app=WhatsApp screenshot=True |
| 1437 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1438 | ok | step | fallback=pyobjc_ax |
| 1439 | ok | step | nodes=1 elapsed=0.00s |
| 1440 | ok | observation |  |
| 1441 | ok | observation |  |
| 1442 | ok | forward_task |  |
| 1443 | ok | world_patch | dialog |
| 1444 | ok | goal_status |  |
| 1445 | ok | decision_engine |  |
| 1446 | ok | planner_decision |  |
| 1447 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1448 | ok | step | transition settle |
| 1449 | ok | step | app=WhatsApp screenshot=True |
| 1450 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1451 | ok | step | fallback=pyobjc_ax |
| 1452 | ok | step | nodes=1 elapsed=0.00s |
| 1453 | ok | observation |  |
| 1454 | ok | step | transition poll |
| 1455 | ok | step | app=WhatsApp screenshot=True |
| 1456 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1457 | ok | step | fallback=pyobjc_ax |
| 1458 | ok | step | nodes=1 elapsed=0.00s |
| 1459 | ok | observation |  |
| 1460 | ok | step | transition poll |
| 1461 | ok | step | app=WhatsApp screenshot=True |
| 1462 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1463 | ok | step | fallback=pyobjc_ax |
| 1464 | ok | step | nodes=1 elapsed=0.00s |
| 1465 | ok | observation |  |
| 1466 | ok | step | transition poll |
| 1467 | ok | step | app=WhatsApp screenshot=True |
| 1468 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1469 | ok | step | fallback=pyobjc_ax |
| 1470 | ok | step | nodes=1 elapsed=0.00s |
| 1471 | ok | observation |  |
| 1472 | ok | step | transition poll |
| 1473 | ok | perception_retry |  |
| 1474 | ok | step | perception retry (fusion_agreement_low) |
| 1475 | ok | step | app=WhatsApp screenshot=True |
| 1476 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1477 | ok | step | fallback=pyobjc_ax |
| 1478 | ok | step | nodes=1 elapsed=0.00s |
| 1479 | ok | observation |  |
| 1480 | fail | perception_unsettled |  |
| 1481 | ok | post_observation |  |
| 1482 | ok | post_world_patch |  |
| 1483 | fail | transition_eval |  |
| 1484 | ok | transition_attribution |  |
| 1485 | fail | verification |  |
| 1486 | ok | step | app=WhatsApp screenshot=True |
| 1487 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1488 | ok | step | fallback=pyobjc_ax |
| 1489 | ok | step | nodes=1 elapsed=0.00s |
| 1490 | ok | observation |  |
| 1491 | ok | post_transition_richer_reobserve |  |
| 1492 | fail | forward_predicate_rollback |  |
| 1493 | ok | step | app=WhatsApp screenshot=True |
| 1494 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1495 | ok | step | fallback=pyobjc_ax |
| 1496 | ok | step | nodes=1 elapsed=0.01s |
| 1497 | ok | observation |  |
| 1498 | ok | observation |  |
| 1499 | ok | forward_task |  |
| 1500 | ok | world_patch | dialog |
| 1501 | ok | goal_status |  |
| 1502 | ok | decision_engine |  |
| 1503 | ok | planner_decision |  |
| 1504 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1505 | ok | step | app=WhatsApp screenshot=True |
| 1506 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1507 | ok | step | fallback=pyobjc_ax |
| 1508 | ok | step | nodes=1 elapsed=0.00s |
| 1509 | ok | observation |  |
| 1510 | ok | observation |  |
| 1511 | ok | forward_task |  |
| 1512 | ok | world_patch | dialog |
| 1513 | ok | goal_status |  |
| 1514 | ok | decision_engine |  |
| 1515 | ok | planner_decision |  |
| 1516 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1517 | ok | step | app=WhatsApp screenshot=True |
| 1518 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1519 | ok | step | fallback=pyobjc_ax |
| 1520 | ok | step | nodes=1 elapsed=0.00s |
| 1521 | ok | observation |  |
| 1522 | ok | observation |  |
| 1523 | ok | forward_task |  |
| 1524 | ok | world_patch | dialog |
| 1525 | ok | goal_status |  |
| 1526 | ok | decision_engine |  |
| 1527 | ok | planner_decision |  |
| 1528 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1529 | ok | step | transition settle |
| 1530 | ok | step | app=WhatsApp screenshot=True |
| 1531 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1532 | ok | step | fallback=pyobjc_ax |
| 1533 | ok | step | nodes=1 elapsed=0.00s |
| 1534 | ok | observation |  |
| 1535 | ok | step | transition poll |
| 1536 | ok | step | app=WhatsApp screenshot=True |
| 1537 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1538 | ok | step | fallback=pyobjc_ax |
| 1539 | ok | step | nodes=1 elapsed=0.00s |
| 1540 | ok | observation |  |
| 1541 | ok | step | transition poll |
| 1542 | ok | step | app=WhatsApp screenshot=True |
| 1543 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1544 | ok | step | fallback=pyobjc_ax |
| 1545 | ok | step | nodes=1 elapsed=0.00s |
| 1546 | ok | observation |  |
| 1547 | ok | step | transition poll |
| 1548 | ok | perception_retry |  |
| 1549 | ok | step | perception retry (fusion_agreement_low) |
| 1550 | ok | step | app=WhatsApp screenshot=True |
| 1551 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1552 | ok | step | fallback=pyobjc_ax |
| 1553 | ok | step | nodes=1 elapsed=0.00s |
| 1554 | ok | observation |  |
| 1555 | fail | perception_unsettled |  |
| 1556 | ok | post_observation |  |
| 1557 | ok | post_world_patch |  |
| 1558 | fail | transition_eval |  |
| 1559 | ok | transition_attribution |  |
| 1560 | fail | verification |  |
| 1561 | ok | step | app=WhatsApp screenshot=True |
| 1562 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1563 | ok | step | fallback=pyobjc_ax |
| 1564 | ok | step | nodes=1 elapsed=0.00s |
| 1565 | ok | observation |  |
| 1566 | ok | post_transition_richer_reobserve |  |
| 1567 | fail | forward_predicate_rollback |  |
| 1568 | ok | step | app=WhatsApp screenshot=True |
| 1569 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1570 | ok | step | fallback=pyobjc_ax |
| 1571 | ok | step | nodes=1 elapsed=0.00s |
| 1572 | ok | observation |  |
| 1573 | ok | observation |  |
| 1574 | ok | forward_task |  |
| 1575 | ok | world_patch | dialog |
| 1576 | ok | goal_status |  |
| 1577 | ok | decision_engine |  |
| 1578 | ok | planner_decision |  |
| 1579 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1580 | ok | step | app=WhatsApp screenshot=True |
| 1581 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1582 | ok | step | fallback=pyobjc_ax |
| 1583 | ok | step | nodes=1 elapsed=0.00s |
| 1584 | ok | observation |  |
| 1585 | ok | observation |  |
| 1586 | ok | forward_task |  |
| 1587 | ok | world_patch | dialog |
| 1588 | ok | goal_status |  |
| 1589 | ok | decision_engine |  |
| 1590 | ok | planner_decision |  |
| 1591 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1592 | ok | step | app=WhatsApp screenshot=True |
| 1593 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1594 | ok | step | fallback=pyobjc_ax |
| 1595 | ok | step | nodes=1 elapsed=0.00s |
| 1596 | ok | observation |  |
| 1597 | ok | observation |  |
| 1598 | ok | forward_task |  |
| 1599 | ok | world_patch | dialog |
| 1600 | ok | goal_status |  |
| 1601 | ok | decision_engine |  |
| 1602 | ok | planner_decision |  |
| 1603 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1604 | ok | step | transition settle |
| 1605 | ok | step | app=WhatsApp screenshot=True |
| 1606 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1607 | ok | step | fallback=pyobjc_ax |
| 1608 | ok | step | nodes=1 elapsed=0.00s |
| 1609 | ok | observation |  |
| 1610 | ok | step | transition poll |
| 1611 | ok | step | app=WhatsApp screenshot=True |
| 1612 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1613 | ok | step | fallback=pyobjc_ax |
| 1614 | ok | step | nodes=1 elapsed=0.00s |
| 1615 | ok | observation |  |
| 1616 | ok | step | transition poll |
| 1617 | ok | step | app=WhatsApp screenshot=True |
| 1618 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1619 | ok | step | fallback=pyobjc_ax |
| 1620 | ok | step | nodes=1 elapsed=0.00s |
| 1621 | ok | observation |  |
| 1622 | ok | step | transition poll |
| 1623 | ok | step | app=WhatsApp screenshot=True |
| 1624 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1625 | ok | step | fallback=pyobjc_ax |
| 1626 | ok | step | nodes=1 elapsed=0.00s |
| 1627 | ok | observation |  |
| 1628 | ok | step | transition poll |
| 1629 | ok | perception_retry |  |
| 1630 | ok | step | perception retry (fusion_agreement_low) |
| 1631 | ok | step | app=WhatsApp screenshot=True |
| 1632 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1633 | ok | step | fallback=pyobjc_ax |
| 1634 | ok | step | nodes=1 elapsed=0.00s |
| 1635 | ok | observation |  |
| 1636 | fail | perception_unsettled |  |
| 1637 | ok | post_observation |  |
| 1638 | ok | post_world_patch |  |
| 1639 | fail | transition_eval |  |
| 1640 | ok | transition_attribution |  |
| 1641 | fail | verification |  |
| 1642 | ok | step | app=WhatsApp screenshot=True |
| 1643 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1644 | ok | step | fallback=pyobjc_ax |
| 1645 | ok | step | nodes=1 elapsed=0.00s |
| 1646 | ok | observation |  |
| 1647 | ok | post_transition_richer_reobserve |  |
| 1648 | fail | forward_predicate_rollback |  |
| 1649 | ok | step | app=WhatsApp screenshot=True |
| 1650 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1651 | ok | step | fallback=pyobjc_ax |
| 1652 | ok | step | nodes=1 elapsed=0.00s |
| 1653 | ok | observation |  |
| 1654 | ok | observation |  |
| 1655 | ok | forward_task |  |
| 1656 | ok | world_patch | dialog |
| 1657 | ok | goal_status |  |
| 1658 | ok | decision_engine |  |
| 1659 | ok | planner_decision |  |
| 1660 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1661 | ok | step | app=WhatsApp screenshot=True |
| 1662 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1663 | ok | step | fallback=pyobjc_ax |
| 1664 | ok | step | nodes=1 elapsed=0.00s |
| 1665 | ok | observation |  |
| 1666 | ok | observation |  |
| 1667 | ok | forward_task |  |
| 1668 | ok | world_patch | dialog |
| 1669 | ok | goal_status |  |
| 1670 | ok | decision_engine |  |
| 1671 | ok | planner_decision |  |
| 1672 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1673 | ok | step | app=WhatsApp screenshot=True |
| 1674 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1675 | ok | step | fallback=pyobjc_ax |
| 1676 | ok | step | nodes=1 elapsed=0.00s |
| 1677 | ok | observation |  |
| 1678 | ok | observation |  |
| 1679 | ok | forward_task |  |
| 1680 | ok | world_patch | dialog |
| 1681 | ok | goal_status |  |
| 1682 | ok | decision_engine |  |
| 1683 | ok | planner_decision |  |
| 1684 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1685 | ok | step | transition settle |
| 1686 | ok | step | app=WhatsApp screenshot=True |
| 1687 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1688 | ok | step | fallback=pyobjc_ax |
| 1689 | ok | step | nodes=1 elapsed=0.00s |
| 1690 | ok | observation |  |
| 1691 | ok | step | transition poll |
| 1692 | ok | step | app=WhatsApp screenshot=True |
| 1693 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1694 | ok | step | fallback=pyobjc_ax |
| 1695 | ok | step | nodes=1 elapsed=0.00s |
| 1696 | ok | observation |  |
| 1697 | ok | step | transition poll |
| 1698 | ok | step | app=WhatsApp screenshot=True |
| 1699 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1700 | ok | step | fallback=pyobjc_ax |
| 1701 | ok | step | nodes=1 elapsed=0.00s |
| 1702 | ok | observation |  |
| 1703 | ok | step | transition poll |
| 1704 | ok | step | app=WhatsApp screenshot=True |
| 1705 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1706 | ok | step | fallback=pyobjc_ax |
| 1707 | ok | step | nodes=1 elapsed=0.00s |
| 1708 | ok | observation |  |
| 1709 | ok | step | transition poll |
| 1710 | ok | perception_retry |  |
| 1711 | ok | step | perception retry (fusion_agreement_low) |
| 1712 | ok | step | app=WhatsApp screenshot=True |
| 1713 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1714 | ok | step | fallback=pyobjc_ax |
| 1715 | ok | step | nodes=1 elapsed=0.00s |
| 1716 | ok | observation |  |
| 1717 | fail | perception_unsettled |  |
| 1718 | ok | post_observation |  |
| 1719 | ok | post_world_patch |  |
| 1720 | fail | transition_eval |  |
| 1721 | ok | transition_attribution |  |
| 1722 | fail | verification |  |
| 1723 | ok | step | app=WhatsApp screenshot=True |
| 1724 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1725 | ok | step | fallback=pyobjc_ax |
| 1726 | ok | step | nodes=1 elapsed=0.00s |
| 1727 | ok | observation |  |
| 1728 | ok | post_transition_richer_reobserve |  |
| 1729 | fail | forward_predicate_rollback |  |
| 1730 | ok | step | app=WhatsApp screenshot=True |
| 1731 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1732 | ok | step | fallback=pyobjc_ax |
| 1733 | ok | step | nodes=1 elapsed=0.00s |
| 1734 | ok | observation |  |
| 1735 | ok | observation |  |
| 1736 | ok | forward_task |  |
| 1737 | ok | world_patch | dialog |
| 1738 | ok | goal_status |  |
| 1739 | ok | decision_engine |  |
| 1740 | ok | planner_decision |  |
| 1741 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1742 | ok | step | app=WhatsApp screenshot=True |
| 1743 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1744 | ok | step | fallback=pyobjc_ax |
| 1745 | ok | step | nodes=1 elapsed=0.00s |
| 1746 | ok | observation |  |
| 1747 | ok | observation |  |
| 1748 | ok | forward_task |  |
| 1749 | ok | world_patch | dialog |
| 1750 | ok | goal_status |  |
| 1751 | ok | decision_engine |  |
| 1752 | ok | planner_decision |  |
| 1753 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1754 | ok | step | app=WhatsApp screenshot=True |
| 1755 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1756 | ok | step | fallback=pyobjc_ax |
| 1757 | ok | step | nodes=1 elapsed=0.00s |
| 1758 | ok | observation |  |
| 1759 | ok | observation |  |
| 1760 | ok | forward_task |  |
| 1761 | ok | world_patch | dialog |
| 1762 | ok | goal_status |  |
| 1763 | ok | decision_engine |  |
| 1764 | ok | planner_decision |  |
| 1765 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1766 | ok | step | transition settle |
| 1767 | ok | step | app=WhatsApp screenshot=True |
| 1768 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1769 | ok | step | fallback=pyobjc_ax |
| 1770 | ok | step | nodes=1 elapsed=0.00s |
| 1771 | ok | observation |  |
| 1772 | ok | step | transition poll |
| 1773 | ok | step | app=WhatsApp screenshot=True |
| 1774 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1775 | ok | step | fallback=pyobjc_ax |
| 1776 | ok | step | nodes=1 elapsed=0.00s |
| 1777 | ok | observation |  |
| 1778 | ok | step | transition poll |
| 1779 | ok | step | app=WhatsApp screenshot=True |
| 1780 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1781 | ok | step | fallback=pyobjc_ax |
| 1782 | ok | step | nodes=1 elapsed=0.00s |
| 1783 | ok | observation |  |
| 1784 | ok | step | transition poll |
| 1785 | ok | step | app=WhatsApp screenshot=True |
| 1786 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1787 | ok | step | fallback=pyobjc_ax |
| 1788 | ok | step | nodes=1 elapsed=0.00s |
| 1789 | ok | observation |  |
| 1790 | ok | step | transition poll |
| 1791 | ok | perception_retry |  |
| 1792 | ok | step | perception retry (fusion_agreement_low) |
| 1793 | ok | step | app=WhatsApp screenshot=True |
| 1794 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1795 | ok | step | fallback=pyobjc_ax |
| 1796 | ok | step | nodes=1 elapsed=0.00s |
| 1797 | ok | observation |  |
| 1798 | fail | perception_unsettled |  |
| 1799 | ok | post_observation |  |
| 1800 | ok | post_world_patch |  |
| 1801 | fail | transition_eval |  |
| 1802 | ok | transition_attribution |  |
| 1803 | fail | verification |  |
| 1804 | ok | step | app=WhatsApp screenshot=True |
| 1805 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1806 | ok | step | fallback=pyobjc_ax |
| 1807 | ok | step | nodes=1 elapsed=0.00s |
| 1808 | ok | observation |  |
| 1809 | ok | post_transition_richer_reobserve |  |
| 1810 | fail | forward_predicate_rollback |  |
| 1811 | ok | step | app=WhatsApp screenshot=True |
| 1812 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1813 | ok | step | fallback=pyobjc_ax |
| 1814 | ok | step | nodes=1 elapsed=0.00s |
| 1815 | ok | observation |  |
| 1816 | ok | observation |  |
| 1817 | ok | forward_task |  |
| 1818 | ok | world_patch | dialog |
| 1819 | ok | goal_status |  |
| 1820 | ok | decision_engine |  |
| 1821 | ok | planner_decision |  |
| 1822 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1823 | ok | step | app=WhatsApp screenshot=True |
| 1824 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1825 | ok | step | fallback=pyobjc_ax |
| 1826 | ok | step | nodes=1 elapsed=0.00s |
| 1827 | ok | observation |  |
| 1828 | ok | observation |  |
| 1829 | ok | forward_task |  |
| 1830 | ok | world_patch | dialog |
| 1831 | ok | goal_status |  |
| 1832 | ok | decision_engine |  |
| 1833 | ok | planner_decision |  |
| 1834 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1835 | ok | step | app=WhatsApp screenshot=True |
| 1836 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1837 | ok | step | fallback=pyobjc_ax |
| 1838 | ok | step | nodes=1 elapsed=0.00s |
| 1839 | ok | observation |  |
| 1840 | ok | observation |  |
| 1841 | ok | forward_task |  |
| 1842 | ok | world_patch | dialog |
| 1843 | ok | goal_status |  |
| 1844 | ok | decision_engine |  |
| 1845 | ok | planner_decision |  |
| 1846 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1847 | ok | step | transition settle |
| 1848 | ok | step | app=WhatsApp screenshot=True |
| 1849 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1850 | ok | step | fallback=pyobjc_ax |
| 1851 | ok | step | nodes=1 elapsed=0.00s |
| 1852 | ok | observation |  |
| 1853 | ok | step | transition poll |
| 1854 | ok | step | app=WhatsApp screenshot=True |
| 1855 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1856 | ok | step | fallback=pyobjc_ax |
| 1857 | ok | step | nodes=1 elapsed=0.00s |
| 1858 | ok | observation |  |
| 1859 | ok | step | transition poll |
| 1860 | ok | step | app=WhatsApp screenshot=True |
| 1861 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1862 | ok | step | fallback=pyobjc_ax |
| 1863 | ok | step | nodes=1 elapsed=0.00s |
| 1864 | ok | observation |  |
| 1865 | ok | step | transition poll |
| 1866 | ok | step | app=WhatsApp screenshot=True |
| 1867 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1868 | ok | step | fallback=pyobjc_ax |
| 1869 | ok | step | nodes=1 elapsed=0.00s |
| 1870 | ok | observation |  |
| 1871 | ok | step | transition poll |
| 1872 | ok | perception_retry |  |
| 1873 | ok | step | perception retry (fusion_agreement_low) |
| 1874 | ok | step | app=WhatsApp screenshot=True |
| 1875 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1876 | ok | step | fallback=pyobjc_ax |
| 1877 | ok | step | nodes=1 elapsed=0.00s |
| 1878 | ok | observation |  |
| 1879 | fail | perception_unsettled |  |
| 1880 | ok | post_observation |  |
| 1881 | ok | post_world_patch |  |
| 1882 | fail | transition_eval |  |
| 1883 | ok | transition_attribution |  |
| 1884 | fail | verification |  |
| 1885 | ok | step | app=WhatsApp screenshot=True |
| 1886 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1887 | ok | step | fallback=pyobjc_ax |
| 1888 | ok | step | nodes=1 elapsed=0.00s |
| 1889 | ok | observation |  |
| 1890 | ok | post_transition_richer_reobserve |  |
| 1891 | fail | forward_predicate_rollback |  |
| 1892 | ok | step | app=WhatsApp screenshot=True |
| 1893 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1894 | ok | step | fallback=pyobjc_ax |
| 1895 | ok | step | nodes=1 elapsed=0.00s |
| 1896 | ok | observation |  |
| 1897 | ok | observation |  |
| 1898 | ok | forward_task |  |
| 1899 | ok | world_patch | dialog |
| 1900 | ok | goal_status |  |
| 1901 | ok | decision_engine |  |
| 1902 | ok | planner_decision |  |
| 1903 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1904 | ok | step | app=WhatsApp screenshot=True |
| 1905 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1906 | ok | step | fallback=pyobjc_ax |
| 1907 | ok | step | nodes=1 elapsed=0.00s |
| 1908 | ok | observation |  |
| 1909 | ok | observation |  |
| 1910 | ok | forward_task |  |
| 1911 | ok | world_patch | dialog |
| 1912 | ok | goal_status |  |
| 1913 | ok | decision_engine |  |
| 1914 | ok | planner_decision |  |
| 1915 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1916 | ok | step | app=WhatsApp screenshot=True |
| 1917 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1918 | ok | step | fallback=pyobjc_ax |
| 1919 | ok | step | nodes=1 elapsed=0.00s |
| 1920 | ok | observation |  |
| 1921 | ok | observation |  |
| 1922 | ok | forward_task |  |
| 1923 | ok | world_patch | dialog |
| 1924 | ok | goal_status |  |
| 1925 | ok | decision_engine |  |
| 1926 | ok | planner_decision |  |
| 1927 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1928 | ok | step | transition settle |
| 1929 | ok | step | app=WhatsApp screenshot=True |
| 1930 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1931 | ok | step | fallback=pyobjc_ax |
| 1932 | ok | step | nodes=1 elapsed=0.00s |
| 1933 | ok | observation |  |
| 1934 | ok | step | transition poll |
| 1935 | ok | step | app=WhatsApp screenshot=True |
| 1936 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1937 | ok | step | fallback=pyobjc_ax |
| 1938 | ok | step | nodes=1 elapsed=0.00s |
| 1939 | ok | observation |  |
| 1940 | ok | step | transition poll |
| 1941 | ok | step | app=WhatsApp screenshot=True |
| 1942 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1943 | ok | step | fallback=pyobjc_ax |
| 1944 | ok | step | nodes=1 elapsed=0.00s |
| 1945 | ok | observation |  |
| 1946 | ok | step | transition poll |
| 1947 | ok | perception_retry |  |
| 1948 | ok | step | perception retry (fusion_agreement_low) |
| 1949 | ok | step | app=WhatsApp screenshot=True |
| 1950 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1951 | ok | step | fallback=pyobjc_ax |
| 1952 | ok | step | nodes=1 elapsed=0.00s |
| 1953 | ok | observation |  |
| 1954 | fail | perception_unsettled |  |
| 1955 | ok | post_observation |  |
| 1956 | ok | post_world_patch |  |
| 1957 | fail | transition_eval |  |
| 1958 | ok | transition_attribution |  |
| 1959 | fail | verification |  |
| 1960 | ok | step | app=WhatsApp screenshot=True |
| 1961 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1962 | ok | step | fallback=pyobjc_ax |
| 1963 | ok | step | nodes=1 elapsed=0.00s |
| 1964 | ok | observation |  |
| 1965 | ok | post_transition_richer_reobserve |  |
| 1966 | fail | forward_predicate_rollback |  |
| 1967 | ok | step | app=WhatsApp screenshot=True |
| 1968 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1969 | ok | step | fallback=pyobjc_ax |
| 1970 | ok | step | nodes=1 elapsed=0.00s |
| 1971 | ok | observation |  |
| 1972 | ok | observation |  |
| 1973 | ok | forward_task |  |
| 1974 | ok | world_patch | dialog |
| 1975 | ok | goal_status |  |
| 1976 | ok | decision_engine |  |
| 1977 | ok | planner_decision |  |
| 1978 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1979 | ok | step | app=WhatsApp screenshot=True |
| 1980 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1981 | ok | step | fallback=pyobjc_ax |
| 1982 | ok | step | nodes=1 elapsed=0.00s |
| 1983 | ok | observation |  |
| 1984 | ok | observation |  |
| 1985 | ok | forward_task |  |
| 1986 | ok | world_patch | dialog |
| 1987 | ok | goal_status |  |
| 1988 | ok | decision_engine |  |
| 1989 | ok | planner_decision |  |
| 1990 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1991 | ok | step | app=WhatsApp screenshot=True |
| 1992 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1993 | ok | step | fallback=pyobjc_ax |
| 1994 | ok | step | nodes=1 elapsed=0.00s |
| 1995 | ok | observation |  |
| 1996 | ok | observation |  |
| 1997 | ok | forward_task |  |
| 1998 | ok | world_patch | dialog |
| 1999 | ok | goal_status |  |
| 2000 | ok | decision_engine |  |
| 2001 | ok | planner_decision |  |
| 2002 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2003 | ok | step | transition settle |
| 2004 | ok | step | app=WhatsApp screenshot=True |
| 2005 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2006 | ok | step | fallback=pyobjc_ax |
| 2007 | ok | step | nodes=1 elapsed=0.00s |
| 2008 | ok | observation |  |
| 2009 | ok | step | transition poll |
| 2010 | ok | step | app=WhatsApp screenshot=True |
| 2011 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2012 | ok | step | fallback=pyobjc_ax |
| 2013 | ok | step | nodes=1 elapsed=0.00s |
| 2014 | ok | observation |  |
| 2015 | ok | step | transition poll |
| 2016 | ok | step | app=WhatsApp screenshot=True |
| 2017 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2018 | ok | step | fallback=pyobjc_ax |
| 2019 | ok | step | nodes=1 elapsed=0.00s |
| 2020 | ok | observation |  |
| 2021 | ok | step | transition poll |
| 2022 | ok | step | app=WhatsApp screenshot=True |
| 2023 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2024 | ok | step | fallback=pyobjc_ax |
| 2025 | ok | step | nodes=1 elapsed=0.00s |
| 2026 | ok | observation |  |
| 2027 | ok | step | transition poll |
| 2028 | ok | perception_retry |  |
| 2029 | ok | step | perception retry (fusion_agreement_low) |
| 2030 | ok | step | app=WhatsApp screenshot=True |
| 2031 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2032 | ok | step | fallback=pyobjc_ax |
| 2033 | ok | step | nodes=1 elapsed=0.00s |
| 2034 | ok | observation |  |
| 2035 | fail | perception_unsettled |  |
| 2036 | ok | post_observation |  |
| 2037 | ok | post_world_patch |  |
| 2038 | fail | transition_eval |  |
| 2039 | ok | transition_attribution |  |
| 2040 | fail | verification |  |
| 2041 | ok | step | app=WhatsApp screenshot=True |
| 2042 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2043 | ok | step | fallback=pyobjc_ax |
| 2044 | ok | step | nodes=1 elapsed=0.00s |
| 2045 | ok | observation |  |
| 2046 | ok | post_transition_richer_reobserve |  |
| 2047 | fail | forward_predicate_rollback |  |
| 2048 | ok | step | app=WhatsApp screenshot=True |
| 2049 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2050 | ok | step | fallback=pyobjc_ax |
| 2051 | ok | step | nodes=1 elapsed=0.00s |
| 2052 | ok | observation |  |
| 2053 | ok | observation |  |
| 2054 | ok | forward_task |  |
| 2055 | ok | world_patch | dialog |
| 2056 | ok | goal_status |  |
| 2057 | ok | decision_engine |  |
| 2058 | ok | planner_decision |  |
| 2059 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2060 | ok | step | app=WhatsApp screenshot=True |
| 2061 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2062 | ok | step | fallback=pyobjc_ax |
| 2063 | ok | step | nodes=1 elapsed=0.00s |
| 2064 | ok | observation |  |
| 2065 | ok | observation |  |
| 2066 | ok | forward_task |  |
| 2067 | ok | world_patch | dialog |
| 2068 | ok | goal_status |  |
| 2069 | ok | decision_engine |  |
| 2070 | ok | planner_decision |  |
| 2071 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2072 | ok | step | app=WhatsApp screenshot=True |
| 2073 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2074 | ok | step | fallback=pyobjc_ax |
| 2075 | ok | step | nodes=1 elapsed=0.00s |
| 2076 | ok | observation |  |
| 2077 | ok | observation |  |
| 2078 | ok | forward_task |  |
| 2079 | ok | world_patch | dialog |
| 2080 | ok | goal_status |  |
| 2081 | ok | decision_engine |  |
| 2082 | ok | planner_decision |  |
| 2083 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2084 | ok | step | transition settle |
| 2085 | ok | step | app=WhatsApp screenshot=True |
| 2086 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2087 | ok | step | fallback=pyobjc_ax |
| 2088 | ok | step | nodes=1 elapsed=0.00s |
| 2089 | ok | observation |  |
| 2090 | ok | step | transition poll |
| 2091 | ok | step | app=WhatsApp screenshot=True |
| 2092 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2093 | ok | step | fallback=pyobjc_ax |
| 2094 | ok | step | nodes=1 elapsed=0.00s |
| 2095 | ok | observation |  |
| 2096 | ok | step | transition poll |
| 2097 | ok | step | app=WhatsApp screenshot=True |
| 2098 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2099 | ok | step | fallback=pyobjc_ax |
| 2100 | ok | step | nodes=1 elapsed=0.00s |
| 2101 | ok | observation |  |
| 2102 | ok | step | transition poll |
| 2103 | ok | step | app=WhatsApp screenshot=True |
| 2104 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2105 | ok | step | fallback=pyobjc_ax |
| 2106 | ok | step | nodes=1 elapsed=0.00s |
| 2107 | ok | observation |  |
| 2108 | ok | step | transition poll |
| 2109 | ok | perception_retry |  |
| 2110 | ok | step | perception retry (fusion_agreement_low) |
| 2111 | ok | step | app=WhatsApp screenshot=True |
| 2112 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2113 | ok | step | fallback=pyobjc_ax |
| 2114 | ok | step | nodes=1 elapsed=0.00s |
| 2115 | ok | observation |  |
| 2116 | fail | perception_unsettled |  |
| 2117 | ok | post_observation |  |
| 2118 | ok | post_world_patch |  |
| 2119 | fail | transition_eval |  |
| 2120 | ok | transition_attribution |  |
| 2121 | fail | verification |  |
| 2122 | ok | step | app=WhatsApp screenshot=True |
| 2123 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2124 | ok | step | fallback=pyobjc_ax |
| 2125 | ok | step | nodes=1 elapsed=0.00s |
| 2126 | ok | observation |  |
| 2127 | ok | post_transition_richer_reobserve |  |
| 2128 | fail | forward_predicate_rollback |  |
| 2129 | ok | step | app=WhatsApp screenshot=True |
| 2130 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2131 | ok | step | fallback=pyobjc_ax |
| 2132 | ok | step | nodes=1 elapsed=0.00s |
| 2133 | ok | observation |  |
| 2134 | ok | observation |  |
| 2135 | ok | forward_task |  |
| 2136 | ok | world_patch | dialog |
| 2137 | ok | goal_status |  |
| 2138 | ok | decision_engine |  |
| 2139 | ok | planner_decision |  |
| 2140 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2141 | ok | step | app=WhatsApp screenshot=True |
| 2142 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2143 | ok | step | fallback=pyobjc_ax |
| 2144 | ok | step | nodes=1 elapsed=0.00s |
| 2145 | ok | observation |  |
| 2146 | ok | observation |  |
| 2147 | ok | forward_task |  |
| 2148 | ok | world_patch | dialog |
| 2149 | ok | goal_status |  |
| 2150 | ok | decision_engine |  |
| 2151 | ok | planner_decision |  |
| 2152 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2153 | ok | step | app=WhatsApp screenshot=True |
| 2154 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2155 | ok | step | fallback=pyobjc_ax |
| 2156 | ok | step | nodes=1 elapsed=0.00s |
| 2157 | ok | observation |  |
| 2158 | ok | observation |  |
| 2159 | ok | forward_task |  |
| 2160 | ok | world_patch | dialog |
| 2161 | ok | goal_status |  |
| 2162 | ok | decision_engine |  |
| 2163 | ok | planner_decision |  |
| 2164 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2165 | ok | step | transition settle |
| 2166 | ok | step | app=WhatsApp screenshot=True |
| 2167 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2168 | ok | step | fallback=pyobjc_ax |
| 2169 | ok | step | nodes=1 elapsed=0.00s |
| 2170 | ok | observation |  |
| 2171 | ok | step | transition poll |
| 2172 | ok | step | app=WhatsApp screenshot=True |
| 2173 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2174 | ok | step | fallback=pyobjc_ax |
| 2175 | ok | step | nodes=1 elapsed=0.00s |
| 2176 | ok | observation |  |
| 2177 | ok | step | transition poll |
| 2178 | ok | step | app=WhatsApp screenshot=True |
| 2179 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2180 | ok | step | fallback=pyobjc_ax |
| 2181 | ok | step | nodes=1 elapsed=0.00s |
| 2182 | ok | observation |  |
| 2183 | ok | step | transition poll |
| 2184 | ok | perception_retry |  |
| 2185 | ok | step | perception retry (fusion_agreement_low) |
| 2186 | ok | step | app=WhatsApp screenshot=True |
| 2187 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2188 | ok | step | fallback=pyobjc_ax |
| 2189 | ok | step | nodes=1 elapsed=0.00s |
| 2190 | ok | observation |  |
| 2191 | fail | perception_unsettled |  |
| 2192 | ok | post_observation |  |
| 2193 | ok | post_world_patch |  |
| 2194 | fail | transition_eval |  |
| 2195 | ok | transition_attribution |  |
| 2196 | fail | verification |  |
| 2197 | ok | step | app=WhatsApp screenshot=True |
| 2198 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2199 | ok | step | fallback=pyobjc_ax |
| 2200 | ok | step | nodes=1 elapsed=0.00s |
| 2201 | ok | observation |  |
| 2202 | ok | post_transition_richer_reobserve |  |
| 2203 | fail | forward_predicate_rollback |  |
| 2204 | ok | step | app=WhatsApp screenshot=True |
| 2205 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2206 | ok | step | fallback=pyobjc_ax |
| 2207 | ok | step | nodes=1 elapsed=0.00s |
| 2208 | ok | observation |  |
| 2209 | ok | observation |  |
| 2210 | ok | forward_task |  |
| 2211 | ok | world_patch | dialog |
| 2212 | ok | goal_status |  |
| 2213 | ok | decision_engine |  |
| 2214 | ok | planner_decision |  |
| 2215 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2216 | ok | step | app=WhatsApp screenshot=True |
| 2217 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2218 | ok | step | fallback=pyobjc_ax |
| 2219 | ok | step | nodes=1 elapsed=0.00s |
| 2220 | ok | observation |  |
| 2221 | ok | observation |  |
| 2222 | ok | forward_task |  |
| 2223 | ok | world_patch | dialog |
| 2224 | ok | goal_status |  |
| 2225 | ok | decision_engine |  |
| 2226 | ok | planner_decision |  |
| 2227 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2228 | ok | step | app=WhatsApp screenshot=True |
| 2229 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2230 | ok | step | fallback=pyobjc_ax |
| 2231 | ok | step | nodes=1 elapsed=0.00s |
| 2232 | ok | observation |  |
| 2233 | ok | observation |  |
| 2234 | ok | forward_task |  |
| 2235 | ok | world_patch | dialog |
| 2236 | ok | goal_status |  |
| 2237 | ok | decision_engine |  |
| 2238 | ok | planner_decision |  |
| 2239 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2240 | ok | step | transition settle |
| 2241 | ok | step | app=WhatsApp screenshot=True |
| 2242 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2243 | ok | step | fallback=pyobjc_ax |
| 2244 | ok | step | nodes=1 elapsed=0.00s |
| 2245 | ok | observation |  |
| 2246 | ok | step | transition poll |
| 2247 | ok | step | app=WhatsApp screenshot=True |
| 2248 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2249 | ok | step | fallback=pyobjc_ax |
| 2250 | ok | step | nodes=1 elapsed=0.00s |
| 2251 | ok | observation |  |
| 2252 | ok | step | transition poll |
| 2253 | ok | step | app=WhatsApp screenshot=True |
| 2254 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2255 | ok | step | fallback=pyobjc_ax |
| 2256 | ok | step | nodes=1 elapsed=0.00s |
| 2257 | ok | observation |  |
| 2258 | ok | step | transition poll |
| 2259 | ok | step | app=WhatsApp screenshot=True |
| 2260 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2261 | ok | step | fallback=pyobjc_ax |
| 2262 | ok | step | nodes=1 elapsed=0.00s |
| 2263 | ok | observation |  |
| 2264 | ok | step | transition poll |
| 2265 | ok | perception_retry |  |
| 2266 | ok | step | perception retry (fusion_agreement_low) |
| 2267 | ok | step | app=WhatsApp screenshot=True |
| 2268 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2269 | ok | step | fallback=pyobjc_ax |
| 2270 | ok | step | nodes=1 elapsed=0.00s |
| 2271 | ok | observation |  |
| 2272 | fail | perception_unsettled |  |
| 2273 | ok | post_observation |  |
| 2274 | ok | post_world_patch |  |
| 2275 | fail | transition_eval |  |
| 2276 | ok | transition_attribution |  |
| 2277 | fail | verification |  |
| 2278 | ok | step | app=WhatsApp screenshot=True |
| 2279 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2280 | ok | step | fallback=pyobjc_ax |
| 2281 | ok | step | nodes=1 elapsed=0.00s |
| 2282 | ok | observation |  |
| 2283 | ok | post_transition_richer_reobserve |  |
| 2284 | fail | forward_predicate_rollback |  |
| 2285 | ok | step | app=WhatsApp screenshot=True |
| 2286 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2287 | ok | step | fallback=pyobjc_ax |
| 2288 | ok | step | nodes=1 elapsed=0.00s |
| 2289 | ok | observation |  |
| 2290 | ok | observation |  |
| 2291 | ok | forward_task |  |
| 2292 | ok | world_patch | dialog |
| 2293 | ok | goal_status |  |
| 2294 | ok | decision_engine |  |
| 2295 | ok | planner_decision |  |
| 2296 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2297 | ok | step | app=WhatsApp screenshot=True |
| 2298 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2299 | ok | step | fallback=pyobjc_ax |
| 2300 | ok | step | nodes=1 elapsed=0.00s |
| 2301 | ok | observation |  |
| 2302 | ok | observation |  |
| 2303 | ok | forward_task |  |
| 2304 | ok | world_patch | dialog |
| 2305 | ok | goal_status |  |
| 2306 | ok | decision_engine |  |
| 2307 | ok | planner_decision |  |
| 2308 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2309 | ok | step | app=WhatsApp screenshot=True |
| 2310 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2311 | ok | step | fallback=pyobjc_ax |
| 2312 | ok | step | nodes=1 elapsed=0.00s |
| 2313 | ok | observation |  |
| 2314 | ok | observation |  |
| 2315 | ok | forward_task |  |
| 2316 | ok | world_patch | dialog |
| 2317 | ok | goal_status |  |
| 2318 | ok | decision_engine |  |
| 2319 | ok | planner_decision |  |
| 2320 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2321 | ok | step | transition settle |
| 2322 | ok | step | app=WhatsApp screenshot=True |
| 2323 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2324 | ok | step | fallback=pyobjc_ax |
| 2325 | ok | step | nodes=1 elapsed=0.00s |
| 2326 | ok | observation |  |
| 2327 | ok | step | transition poll |
| 2328 | ok | step | app=WhatsApp screenshot=True |
| 2329 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2330 | ok | step | fallback=pyobjc_ax |
| 2331 | ok | step | nodes=1 elapsed=0.00s |
| 2332 | ok | observation |  |
| 2333 | ok | step | transition poll |
| 2334 | ok | step | app=WhatsApp screenshot=True |
| 2335 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2336 | ok | step | fallback=pyobjc_ax |
| 2337 | ok | step | nodes=1 elapsed=0.00s |
| 2338 | ok | observation |  |
| 2339 | ok | step | transition poll |
| 2340 | ok | perception_retry |  |
| 2341 | ok | step | perception retry (fusion_agreement_low) |
| 2342 | ok | step | app=WhatsApp screenshot=True |
| 2343 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2344 | ok | step | fallback=pyobjc_ax |
| 2345 | ok | step | nodes=1 elapsed=0.00s |
| 2346 | ok | observation |  |
| 2347 | fail | perception_unsettled |  |
| 2348 | ok | post_observation |  |
| 2349 | ok | post_world_patch |  |
| 2350 | fail | transition_eval |  |
| 2351 | ok | transition_attribution |  |
| 2352 | fail | verification |  |
| 2353 | ok | step | app=WhatsApp screenshot=True |
| 2354 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2355 | ok | step | fallback=pyobjc_ax |
| 2356 | ok | step | nodes=1 elapsed=0.00s |
| 2357 | ok | observation |  |
| 2358 | ok | post_transition_richer_reobserve |  |
| 2359 | fail | forward_predicate_rollback |  |
| 2360 | ok | step | app=WhatsApp screenshot=True |
| 2361 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2362 | ok | step | fallback=pyobjc_ax |
| 2363 | ok | step | nodes=1 elapsed=0.00s |
| 2364 | ok | observation |  |
| 2365 | ok | observation |  |
| 2366 | ok | forward_task |  |
| 2367 | ok | world_patch | dialog |
| 2368 | ok | goal_status |  |
| 2369 | ok | decision_engine |  |
| 2370 | ok | planner_decision |  |
| 2371 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2372 | ok | step | app=WhatsApp screenshot=True |
| 2373 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2374 | ok | step | fallback=pyobjc_ax |
| 2375 | ok | step | nodes=1 elapsed=0.00s |
| 2376 | ok | observation |  |
| 2377 | ok | observation |  |
| 2378 | ok | forward_task |  |
| 2379 | ok | world_patch | dialog |
| 2380 | ok | goal_status |  |
| 2381 | ok | decision_engine |  |
| 2382 | ok | planner_decision |  |
| 2383 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2384 | ok | step | app=WhatsApp screenshot=True |
| 2385 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2386 | ok | step | fallback=pyobjc_ax |
| 2387 | ok | step | nodes=1 elapsed=0.00s |
| 2388 | ok | observation |  |
| 2389 | ok | observation |  |
| 2390 | ok | forward_task |  |
| 2391 | ok | world_patch | dialog |
| 2392 | ok | goal_status |  |
| 2393 | ok | decision_engine |  |
| 2394 | ok | planner_decision |  |
| 2395 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2396 | ok | step | transition settle |
| 2397 | ok | step | app=WhatsApp screenshot=True |
| 2398 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2399 | ok | step | fallback=pyobjc_ax |
| 2400 | ok | step | nodes=1 elapsed=0.00s |
| 2401 | ok | observation |  |
| 2402 | ok | step | transition poll |
| 2403 | ok | step | app=WhatsApp screenshot=True |
| 2404 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2405 | ok | step | fallback=pyobjc_ax |
| 2406 | ok | step | nodes=1 elapsed=0.00s |
| 2407 | ok | observation |  |
| 2408 | ok | step | transition poll |
| 2409 | ok | step | app=WhatsApp screenshot=True |
| 2410 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2411 | ok | step | fallback=pyobjc_ax |
| 2412 | ok | step | nodes=1 elapsed=0.00s |
| 2413 | ok | observation |  |
| 2414 | ok | step | transition poll |
| 2415 | ok | step | app=WhatsApp screenshot=True |
| 2416 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2417 | ok | step | fallback=pyobjc_ax |
| 2418 | ok | step | nodes=1 elapsed=0.00s |
| 2419 | ok | observation |  |
| 2420 | ok | step | transition poll |
| 2421 | ok | perception_retry |  |
| 2422 | ok | step | perception retry (fusion_agreement_low) |
| 2423 | ok | step | app=WhatsApp screenshot=True |
| 2424 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2425 | ok | step | fallback=pyobjc_ax |
| 2426 | ok | step | nodes=1 elapsed=0.00s |
| 2427 | ok | observation |  |
| 2428 | fail | perception_unsettled |  |
| 2429 | ok | post_observation |  |
| 2430 | ok | post_world_patch |  |
| 2431 | fail | transition_eval |  |
| 2432 | ok | transition_attribution |  |
| 2433 | fail | verification |  |
| 2434 | ok | step | app=WhatsApp screenshot=True |
| 2435 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2436 | ok | step | fallback=pyobjc_ax |
| 2437 | ok | step | nodes=1 elapsed=0.00s |
| 2438 | ok | observation |  |
| 2439 | ok | post_transition_richer_reobserve |  |
| 2440 | fail | forward_predicate_rollback |  |
| 2441 | ok | step | app=WhatsApp screenshot=True |
| 2442 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2443 | ok | step | fallback=pyobjc_ax |
| 2444 | ok | step | nodes=1 elapsed=0.00s |
| 2445 | ok | observation |  |
| 2446 | ok | observation |  |
| 2447 | ok | forward_task |  |
| 2448 | ok | world_patch | dialog |
| 2449 | ok | goal_status |  |
| 2450 | ok | decision_engine |  |
| 2451 | ok | planner_decision |  |
| 2452 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2453 | ok | step | app=WhatsApp screenshot=True |
| 2454 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2455 | ok | step | fallback=pyobjc_ax |
| 2456 | ok | step | nodes=1 elapsed=0.00s |
| 2457 | ok | observation |  |
| 2458 | ok | observation |  |
| 2459 | ok | forward_task |  |
| 2460 | ok | world_patch | dialog |
| 2461 | ok | goal_status |  |
| 2462 | ok | decision_engine |  |
| 2463 | ok | planner_decision |  |
| 2464 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2465 | ok | step | app=WhatsApp screenshot=True |
| 2466 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2467 | ok | step | fallback=pyobjc_ax |
| 2468 | ok | step | nodes=1 elapsed=0.00s |
| 2469 | ok | observation |  |
| 2470 | ok | observation |  |
| 2471 | ok | forward_task |  |
| 2472 | ok | world_patch | dialog |
| 2473 | ok | goal_status |  |
| 2474 | ok | decision_engine |  |
| 2475 | ok | planner_decision |  |
| 2476 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2477 | ok | step | transition settle |
| 2478 | ok | step | app=WhatsApp screenshot=True |
| 2479 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2480 | ok | step | fallback=pyobjc_ax |
| 2481 | ok | step | nodes=1 elapsed=0.00s |
| 2482 | ok | observation |  |
| 2483 | ok | step | transition poll |
| 2484 | ok | step | app=WhatsApp screenshot=True |
| 2485 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2486 | ok | step | fallback=pyobjc_ax |
| 2487 | ok | step | nodes=1 elapsed=0.00s |
| 2488 | ok | observation |  |
| 2489 | ok | step | transition poll |
| 2490 | ok | step | app=WhatsApp screenshot=True |
| 2491 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2492 | ok | step | fallback=pyobjc_ax |
| 2493 | ok | step | nodes=1 elapsed=0.00s |
| 2494 | ok | observation |  |
| 2495 | ok | step | transition poll |
| 2496 | ok | step | app=WhatsApp screenshot=True |
| 2497 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2498 | ok | step | fallback=pyobjc_ax |
| 2499 | ok | step | nodes=1 elapsed=0.00s |
| 2500 | ok | observation |  |
| 2501 | ok | step | transition poll |
| 2502 | ok | perception_retry |  |
| 2503 | ok | step | perception retry (fusion_agreement_low) |
| 2504 | ok | step | app=WhatsApp screenshot=True |
| 2505 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2506 | ok | step | fallback=pyobjc_ax |
| 2507 | ok | step | nodes=1 elapsed=0.00s |
| 2508 | ok | observation |  |
| 2509 | fail | perception_unsettled |  |
| 2510 | ok | post_observation |  |
| 2511 | ok | post_world_patch |  |
| 2512 | fail | transition_eval |  |
| 2513 | ok | transition_attribution |  |
| 2514 | fail | verification |  |
| 2515 | ok | step | app=WhatsApp screenshot=True |
| 2516 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2517 | ok | step | fallback=pyobjc_ax |
| 2518 | ok | step | nodes=1 elapsed=0.00s |
| 2519 | ok | observation |  |
| 2520 | ok | post_transition_richer_reobserve |  |
| 2521 | fail | forward_predicate_rollback |  |
| 2522 | ok | step | app=WhatsApp screenshot=True |
| 2523 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2524 | ok | step | fallback=pyobjc_ax |
| 2525 | ok | step | nodes=1 elapsed=0.00s |
| 2526 | ok | observation |  |
| 2527 | ok | observation |  |
| 2528 | ok | forward_task |  |
| 2529 | ok | world_patch | dialog |
| 2530 | ok | goal_status |  |
| 2531 | ok | decision_engine |  |
| 2532 | ok | planner_decision |  |
| 2533 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2534 | ok | step | app=WhatsApp screenshot=True |
| 2535 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2536 | ok | step | fallback=pyobjc_ax |
| 2537 | ok | step | nodes=1 elapsed=0.00s |
| 2538 | ok | observation |  |
| 2539 | ok | observation |  |
| 2540 | ok | forward_task |  |
| 2541 | ok | world_patch | dialog |
| 2542 | ok | goal_status |  |
| 2543 | ok | decision_engine |  |
| 2544 | ok | planner_decision |  |
| 2545 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2546 | ok | step | app=WhatsApp screenshot=True |
| 2547 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2548 | ok | step | fallback=pyobjc_ax |
| 2549 | ok | step | nodes=1 elapsed=0.00s |
| 2550 | ok | observation |  |
| 2551 | ok | observation |  |
| 2552 | ok | forward_task |  |
| 2553 | ok | world_patch | dialog |
| 2554 | ok | goal_status |  |
| 2555 | ok | decision_engine |  |
| 2556 | ok | planner_decision |  |
| 2557 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2558 | ok | step | transition settle |
| 2559 | ok | step | app=WhatsApp screenshot=True |
| 2560 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2561 | ok | step | fallback=pyobjc_ax |
| 2562 | ok | step | nodes=1 elapsed=0.00s |
| 2563 | ok | observation |  |
| 2564 | ok | step | transition poll |
| 2565 | ok | step | app=WhatsApp screenshot=True |
| 2566 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2567 | ok | step | fallback=pyobjc_ax |
| 2568 | ok | step | nodes=1 elapsed=0.00s |
| 2569 | ok | observation |  |
| 2570 | ok | step | transition poll |
| 2571 | ok | step | app=WhatsApp screenshot=True |
| 2572 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2573 | ok | step | fallback=pyobjc_ax |
| 2574 | ok | step | nodes=1 elapsed=0.00s |
| 2575 | ok | observation |  |
| 2576 | ok | step | transition poll |
| 2577 | ok | step | app=WhatsApp screenshot=True |
| 2578 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2579 | ok | step | fallback=pyobjc_ax |
| 2580 | ok | step | nodes=1 elapsed=0.00s |
| 2581 | ok | observation |  |
| 2582 | ok | step | transition poll |
| 2583 | ok | perception_retry |  |
| 2584 | ok | step | perception retry (fusion_agreement_low) |
| 2585 | ok | step | app=WhatsApp screenshot=True |
| 2586 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2587 | ok | step | fallback=pyobjc_ax |
| 2588 | ok | step | nodes=1 elapsed=0.00s |
| 2589 | ok | observation |  |
| 2590 | fail | perception_unsettled |  |
| 2591 | ok | post_observation |  |
| 2592 | ok | post_world_patch |  |
| 2593 | fail | transition_eval |  |
| 2594 | ok | transition_attribution |  |
| 2595 | fail | verification |  |
| 2596 | ok | step | app=WhatsApp screenshot=True |
| 2597 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2598 | ok | step | fallback=pyobjc_ax |
| 2599 | ok | step | nodes=1 elapsed=0.00s |
| 2600 | ok | observation |  |
| 2601 | ok | post_transition_richer_reobserve |  |
| 2602 | fail | forward_predicate_rollback |  |
| 2603 | ok | step | app=WhatsApp screenshot=True |
| 2604 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2605 | ok | step | fallback=pyobjc_ax |
| 2606 | ok | step | nodes=1 elapsed=0.00s |
| 2607 | ok | observation |  |
| 2608 | ok | observation |  |
| 2609 | ok | forward_task |  |
| 2610 | ok | world_patch | dialog |
| 2611 | ok | goal_status |  |
| 2612 | ok | decision_engine |  |
| 2613 | ok | planner_decision |  |
| 2614 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2615 | ok | step | app=WhatsApp screenshot=True |
| 2616 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2617 | ok | step | fallback=pyobjc_ax |
| 2618 | ok | step | nodes=1 elapsed=0.00s |
| 2619 | ok | observation |  |
| 2620 | ok | observation |  |
| 2621 | ok | forward_task |  |
| 2622 | ok | world_patch | dialog |
| 2623 | ok | goal_status |  |
| 2624 | ok | decision_engine |  |
| 2625 | ok | planner_decision |  |
| 2626 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2627 | ok | step | app=WhatsApp screenshot=True |
| 2628 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2629 | ok | step | fallback=pyobjc_ax |
| 2630 | ok | step | nodes=1 elapsed=0.00s |
| 2631 | ok | observation |  |
| 2632 | ok | observation |  |
| 2633 | ok | forward_task |  |
| 2634 | ok | world_patch | dialog |
| 2635 | ok | goal_status |  |
| 2636 | ok | decision_engine |  |
| 2637 | ok | planner_decision |  |
| 2638 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2639 | ok | step | transition settle |
| 2640 | ok | step | app=WhatsApp screenshot=True |
| 2641 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2642 | ok | step | fallback=pyobjc_ax |
| 2643 | ok | step | nodes=1 elapsed=0.00s |
| 2644 | ok | observation |  |
| 2645 | ok | step | transition poll |
| 2646 | ok | step | app=WhatsApp screenshot=True |
| 2647 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2648 | ok | step | fallback=pyobjc_ax |
| 2649 | ok | step | nodes=1 elapsed=0.00s |
| 2650 | ok | observation |  |
| 2651 | ok | step | transition poll |
| 2652 | ok | step | app=WhatsApp screenshot=True |
| 2653 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2654 | ok | step | fallback=pyobjc_ax |
| 2655 | ok | step | nodes=1 elapsed=0.00s |
| 2656 | ok | observation |  |
| 2657 | ok | step | transition poll |
| 2658 | ok | step | app=WhatsApp screenshot=True |
| 2659 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2660 | ok | step | fallback=pyobjc_ax |
| 2661 | ok | step | nodes=1 elapsed=0.00s |
| 2662 | ok | observation |  |
| 2663 | ok | step | transition poll |
| 2664 | ok | perception_retry |  |
| 2665 | ok | step | perception retry (fusion_agreement_low) |
| 2666 | ok | step | app=WhatsApp screenshot=True |
| 2667 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2668 | ok | step | fallback=pyobjc_ax |
| 2669 | ok | step | nodes=1 elapsed=0.00s |
| 2670 | ok | observation |  |
| 2671 | fail | perception_unsettled |  |
| 2672 | ok | post_observation |  |
| 2673 | ok | post_world_patch |  |
| 2674 | fail | transition_eval |  |
| 2675 | ok | transition_attribution |  |
| 2676 | fail | verification |  |
| 2677 | ok | step | app=WhatsApp screenshot=True |
| 2678 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2679 | ok | step | fallback=pyobjc_ax |
| 2680 | ok | step | nodes=1 elapsed=0.00s |
| 2681 | ok | observation |  |
| 2682 | ok | post_transition_richer_reobserve |  |
| 2683 | fail | forward_predicate_rollback |  |
| 2684 | ok | world_summary |  |
| 2685 | fail | check | fail |
| 2686 | fail | run_end | closed_loop ok=False reason='Maximum step count reached' iterations=97 |

## Failures

- seq=5 `check`: {"ts": 1785219051.991273, "seq": 5, "run_id": "wa-forward-live-1785219051", "kind": "check", "status": "fail", "name": "ghost_cli_installed", "expected": true, "actual": false, "message": "fail", "ste
- seq=61 `perception_unsettled`: {"ts": 1785219119.814075, "seq": 61, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_strat
- seq=64 `transition_eval`: {"ts": 1785219119.829618, "seq": 64, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family": 
- seq=66 `verification`: {"ts": 1785219119.829907, "seq": 66, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=72 `forward_predicate_rollback`: {"ts": 1785219120.4993238, "seq": 72, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=97 `perception_unsettled`: {"ts": 1785219141.052914, "seq": 97, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_strat
- seq=100 `transition_eval`: {"ts": 1785219141.070443, "seq": 100, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=102 `verification`: {"ts": 1785219141.07074, "seq": 102, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=108 `forward_predicate_rollback`: {"ts": 1785219141.810405, "seq": 108, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=138 `perception_unsettled`: {"ts": 1785219158.647449, "seq": 138, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=141 `transition_eval`: {"ts": 1785219158.662438, "seq": 141, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=143 `verification`: {"ts": 1785219158.662796, "seq": 143, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=149 `forward_predicate_rollback`: {"ts": 1785219159.3845499, "seq": 149, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=208 `perception_unsettled`: {"ts": 1785219190.603141, "seq": 208, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=211 `transition_eval`: {"ts": 1785219190.620987, "seq": 211, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=213 `verification`: {"ts": 1785219190.621579, "seq": 213, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=220 `forward_predicate_rollback`: {"ts": 1785219190.750883, "seq": 220, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=283 `perception_unsettled`: {"ts": 1785219203.968839, "seq": 283, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=286 `transition_eval`: {"ts": 1785219203.9839811, "seq": 286, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=288 `verification`: {"ts": 1785219203.9842, "seq": 288, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluator
- seq=295 `forward_predicate_rollback`: {"ts": 1785219204.08379, "seq": 295, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward_
- seq=364 `perception_unsettled`: {"ts": 1785219217.6677508, "seq": 364, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=367 `transition_eval`: {"ts": 1785219217.6830919, "seq": 367, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=369 `verification`: {"ts": 1785219217.683306, "seq": 369, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=376 `forward_predicate_rollback`: {"ts": 1785219217.784279, "seq": 376, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=439 `perception_unsettled`: {"ts": 1785219231.02117, "seq": 439, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_strat
- seq=442 `transition_eval`: {"ts": 1785219231.037017, "seq": 442, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=444 `verification`: {"ts": 1785219231.03726, "seq": 444, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=451 `forward_predicate_rollback`: {"ts": 1785219231.1641579, "seq": 451, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=514 `perception_unsettled`: {"ts": 1785219244.680792, "seq": 514, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=517 `transition_eval`: {"ts": 1785219244.696108, "seq": 517, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=519 `verification`: {"ts": 1785219244.696631, "seq": 519, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=526 `forward_predicate_rollback`: {"ts": 1785219244.820703, "seq": 526, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=595 `perception_unsettled`: {"ts": 1785219258.026835, "seq": 595, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=598 `transition_eval`: {"ts": 1785219258.0416052, "seq": 598, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=600 `verification`: {"ts": 1785219258.041804, "seq": 600, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=607 `forward_predicate_rollback`: {"ts": 1785219258.136151, "seq": 607, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=670 `perception_unsettled`: {"ts": 1785219271.995372, "seq": 670, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=673 `transition_eval`: {"ts": 1785219272.010935, "seq": 673, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=675 `verification`: {"ts": 1785219272.011245, "seq": 675, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=682 `forward_predicate_rollback`: {"ts": 1785219272.135304, "seq": 682, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=751 `perception_unsettled`: {"ts": 1785219285.5637681, "seq": 751, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=754 `transition_eval`: {"ts": 1785219285.5787468, "seq": 754, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=756 `verification`: {"ts": 1785219285.5790122, "seq": 756, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=763 `forward_predicate_rollback`: {"ts": 1785219285.6744168, "seq": 763, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=832 `perception_unsettled`: {"ts": 1785219298.427184, "seq": 832, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=835 `transition_eval`: {"ts": 1785219298.4420228, "seq": 835, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=837 `verification`: {"ts": 1785219298.442482, "seq": 837, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=844 `forward_predicate_rollback`: {"ts": 1785219298.54176, "seq": 844, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward_
- seq=913 `perception_unsettled`: {"ts": 1785219311.5139358, "seq": 913, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=916 `transition_eval`: {"ts": 1785219311.529164, "seq": 916, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=918 `verification`: {"ts": 1785219311.52962, "seq": 918, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=925 `forward_predicate_rollback`: {"ts": 1785219311.625589, "seq": 925, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=994 `perception_unsettled`: {"ts": 1785219322.8471282, "seq": 994, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=997 `transition_eval`: {"ts": 1785219322.862069, "seq": 997, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=999 `verification`: {"ts": 1785219322.86224, "seq": 999, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=1006 `forward_predicate_rollback`: {"ts": 1785219322.959114, "seq": 1006, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1075 `perception_unsettled`: {"ts": 1785219336.2041879, "seq": 1075, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1078 `transition_eval`: {"ts": 1785219336.2200608, "seq": 1078, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1080 `verification`: {"ts": 1785219336.2203362, "seq": 1080, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1087 `forward_predicate_rollback`: {"ts": 1785219336.322786, "seq": 1087, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1156 `perception_unsettled`: {"ts": 1785219349.229095, "seq": 1156, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1159 `transition_eval`: {"ts": 1785219349.244958, "seq": 1159, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1161 `verification`: {"ts": 1785219349.245249, "seq": 1161, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1168 `forward_predicate_rollback`: {"ts": 1785219349.36467, "seq": 1168, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=1237 `perception_unsettled`: {"ts": 1785219363.101989, "seq": 1237, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1240 `transition_eval`: {"ts": 1785219363.1168818, "seq": 1240, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1242 `verification`: {"ts": 1785219363.117079, "seq": 1242, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1249 `forward_predicate_rollback`: {"ts": 1785219363.2137249, "seq": 1249, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=1318 `perception_unsettled`: {"ts": 1785219374.671507, "seq": 1318, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1321 `transition_eval`: {"ts": 1785219374.686204, "seq": 1321, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1323 `verification`: {"ts": 1785219374.686393, "seq": 1323, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1330 `forward_predicate_rollback`: {"ts": 1785219374.782659, "seq": 1330, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1399 `perception_unsettled`: {"ts": 1785219386.547243, "seq": 1399, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1402 `transition_eval`: {"ts": 1785219386.562527, "seq": 1402, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1404 `verification`: {"ts": 1785219386.562737, "seq": 1404, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1411 `forward_predicate_rollback`: {"ts": 1785219386.746357, "seq": 1411, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1480 `perception_unsettled`: {"ts": 1785219399.204156, "seq": 1480, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1483 `transition_eval`: {"ts": 1785219399.220192, "seq": 1483, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1485 `verification`: {"ts": 1785219399.220475, "seq": 1485, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1492 `forward_predicate_rollback`: {"ts": 1785219399.324866, "seq": 1492, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1555 `perception_unsettled`: {"ts": 1785219410.656042, "seq": 1555, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1558 `transition_eval`: {"ts": 1785219410.672074, "seq": 1558, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1560 `verification`: {"ts": 1785219410.672357, "seq": 1560, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1567 `forward_predicate_rollback`: {"ts": 1785219410.8247108, "seq": 1567, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=1636 `perception_unsettled`: {"ts": 1785219423.632597, "seq": 1636, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1639 `transition_eval`: {"ts": 1785219423.649282, "seq": 1639, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1641 `verification`: {"ts": 1785219423.649662, "seq": 1641, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1648 `forward_predicate_rollback`: {"ts": 1785219423.766897, "seq": 1648, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1717 `perception_unsettled`: {"ts": 1785219435.076133, "seq": 1717, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1720 `transition_eval`: {"ts": 1785219435.09132, "seq": 1720, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=1722 `verification`: {"ts": 1785219435.091531, "seq": 1722, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1729 `forward_predicate_rollback`: {"ts": 1785219435.196676, "seq": 1729, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1798 `perception_unsettled`: {"ts": 1785219447.38587, "seq": 1798, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=1801 `transition_eval`: {"ts": 1785219447.401118, "seq": 1801, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1803 `verification`: {"ts": 1785219447.4013638, "seq": 1803, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1810 `forward_predicate_rollback`: {"ts": 1785219447.504968, "seq": 1810, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1879 `perception_unsettled`: {"ts": 1785219459.179033, "seq": 1879, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1882 `transition_eval`: {"ts": 1785219459.1953862, "seq": 1882, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1884 `verification`: {"ts": 1785219459.195772, "seq": 1884, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1891 `forward_predicate_rollback`: {"ts": 1785219459.30811, "seq": 1891, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=1954 `perception_unsettled`: {"ts": 1785219470.808201, "seq": 1954, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1957 `transition_eval`: {"ts": 1785219470.823404, "seq": 1957, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1959 `verification`: {"ts": 1785219470.850833, "seq": 1959, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1966 `forward_predicate_rollback`: {"ts": 1785219470.9531221, "seq": 1966, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2035 `perception_unsettled`: {"ts": 1785219484.807421, "seq": 2035, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2038 `transition_eval`: {"ts": 1785219484.824115, "seq": 2038, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2040 `verification`: {"ts": 1785219484.824696, "seq": 2040, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2047 `forward_predicate_rollback`: {"ts": 1785219484.9441369, "seq": 2047, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2116 `perception_unsettled`: {"ts": 1785219498.863112, "seq": 2116, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2119 `transition_eval`: {"ts": 1785219498.8791208, "seq": 2119, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2121 `verification`: {"ts": 1785219498.87941, "seq": 2121, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=2128 `forward_predicate_rollback`: {"ts": 1785219498.986685, "seq": 2128, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2191 `perception_unsettled`: {"ts": 1785219510.648911, "seq": 2191, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2194 `transition_eval`: {"ts": 1785219510.665084, "seq": 2194, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2196 `verification`: {"ts": 1785219510.665388, "seq": 2196, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2203 `forward_predicate_rollback`: {"ts": 1785219510.82306, "seq": 2203, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=2272 `perception_unsettled`: {"ts": 1785219529.511175, "seq": 2272, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2275 `transition_eval`: {"ts": 1785219529.527818, "seq": 2275, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2277 `verification`: {"ts": 1785219529.528126, "seq": 2277, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2284 `forward_predicate_rollback`: {"ts": 1785219529.7830698, "seq": 2284, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2347 `perception_unsettled`: {"ts": 1785219541.38925, "seq": 2347, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=2350 `transition_eval`: {"ts": 1785219541.406145, "seq": 2350, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2352 `verification`: {"ts": 1785219541.406522, "seq": 2352, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2359 `forward_predicate_rollback`: {"ts": 1785219541.558481, "seq": 2359, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2428 `perception_unsettled`: {"ts": 1785219561.258584, "seq": 2428, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2431 `transition_eval`: {"ts": 1785219561.274868, "seq": 2431, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2433 `verification`: {"ts": 1785219561.275191, "seq": 2433, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2440 `forward_predicate_rollback`: {"ts": 1785219561.382508, "seq": 2440, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2509 `perception_unsettled`: {"ts": 1785219574.926641, "seq": 2509, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2512 `transition_eval`: {"ts": 1785219574.943838, "seq": 2512, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2514 `verification`: {"ts": 1785219575.224816, "seq": 2514, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2521 `forward_predicate_rollback`: {"ts": 1785219575.338737, "seq": 2521, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2590 `perception_unsettled`: {"ts": 1785219590.341596, "seq": 2590, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2593 `transition_eval`: {"ts": 1785219590.359467, "seq": 2593, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2595 `verification`: {"ts": 1785219590.359854, "seq": 2595, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2602 `forward_predicate_rollback`: {"ts": 1785219590.511796, "seq": 2602, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2671 `perception_unsettled`: {"ts": 1785219610.5212312, "seq": 2671, "run_id": "wa-forward-live-1785219051", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=2674 `transition_eval`: {"ts": 1785219610.536511, "seq": 2674, "run_id": "wa-forward-live-1785219051", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2676 `verification`: {"ts": 1785219610.536706, "seq": 2676, "run_id": "wa-forward-live-1785219051", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2683 `forward_predicate_rollback`: {"ts": 1785219610.6380548, "seq": 2683, "run_id": "wa-forward-live-1785219051", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2685 `check`: {"ts": 1785219610.740417, "seq": 2685, "run_id": "wa-forward-live-1785219051", "kind": "check", "status": "fail", "name": "forward_task", "expected": "forward 'zarooratwala' from 'Kulvinder' to 'Palla
- seq=2686 `run_end`: {"ts": 1785219610.7404668, "seq": 2686, "run_id": "wa-forward-live-1785219051", "kind": "run_end", "status": "fail", "ok": false, "detail": "closed_loop ok=False reason='Maximum step count reached' it
