# Run log — `wa-forward-live-1785495667`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260731_163107.jsonl`
- Events: 1893
- Final elapsed: `870.67s`

| seq | status | kind | detail |
|----:|:------:|------|--------|
| 1 | ok | whatsapp_forward_message | find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 2 | ok | step | checking Terminal Accessibility |
| 3 | ok | check | pass |
| 4 | ok | check | pass |
| 5 | fail | check | fail |
| 6 | ok | check | pass |
| 7 | ok | step | launched via open -a WhatsApp |
| 8 | ok | step | WhatsApp startup settle |
| 9 | ok | step | app=WhatsApp screenshot=True |
| 10 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 11 | ok | observation_raw_source |  |
| 12 | ok | observation_raw_source |  |
| 13 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 14 | ok | observation |  |
| 15 | ok | observation_raw |  |
| 16 | ok | world_patch | Screen #1 |
| 17 | ok | step | closed-loop goal=find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 18 | ok | loop_budget |  |
| 19 | ok | progress_clock |  |
| 20 | ok | step | app=WhatsApp screenshot=True |
| 21 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 22 | ok | observation_raw_source |  |
| 23 | ok | observation_raw_source |  |
| 24 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 25 | ok | observation |  |
| 26 | ok | observation_raw |  |
| 27 | ok | observation_raw |  |
| 28 | ok | observation_fused | LIST |
| 29 | ok | observation |  |
| 30 | ok | forward_task |  |
| 31 | ok | world_patch | Screen #1 |
| 32 | ok | fusion_conflicts |  |
| 33 | ok | worldview_low |  |
| 34 | ok | step | low worldview / fusion conflict — re-observe |
| 35 | ok | step | app=WhatsApp screenshot=True |
| 36 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 37 | ok | observation_raw_source |  |
| 38 | ok | observation_raw_source |  |
| 39 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 40 | ok | observation |  |
| 41 | ok | observation_raw |  |
| 42 | ok | observation_raw |  |
| 43 | ok | observation_fused | LIST |
| 44 | ok | goal_status |  |
| 45 | ok | decision_budget |  |
| 46 | ok | decision_engine |  |
| 47 | ok | planner_decision |  |
| 48 | fail | execution | typed 'Kulvinder' into search field label='Search' AXValue='' open='Cmd+F search shortcut' evidence='' attempts=['open=C |
| 49 | fail | transition_attribution |  |
| 50 | warn | progress_clock |  |
| 51 | ok | step | app=WhatsApp screenshot=True |
| 52 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 53 | ok | observation_raw_source |  |
| 54 | ok | observation_raw_source |  |
| 55 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 56 | ok | observation |  |
| 57 | ok | observation_raw |  |
| 58 | ok | observation_raw |  |
| 59 | ok | observation_fused | LIST |
| 60 | ok | observation |  |
| 61 | ok | forward_task |  |
| 62 | ok | world_patch | Screen #1 |
| 63 | ok | fusion_conflicts |  |
| 64 | ok | goal_status |  |
| 65 | ok | decision_budget |  |
| 66 | ok | decision_engine |  |
| 67 | ok | planner_decision |  |
| 68 | ok | execution | open Search via Cmd+F search shortcut |
| 69 | ok | step | transition settle |
| 70 | ok | step | app=WhatsApp screenshot=True |
| 71 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 72 | ok | observation_raw_source |  |
| 73 | ok | observation_raw_source |  |
| 74 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 75 | ok | observation |  |
| 76 | ok | observation_raw |  |
| 77 | ok | observation_raw |  |
| 78 | ok | observation_fused | LIST |
| 79 | ok | step | transition poll |
| 80 | ok | perception_settled |  |
| 81 | ok | post_transition_settled_view | LIST |
| 82 | ok | post_observation |  |
| 83 | ok | post_world_patch |  |
| 84 | fail | transition_eval |  |
| 85 | ok | transition_attribution |  |
| 86 | fail | verification |  |
| 87 | ok | step | app=WhatsApp screenshot=True |
| 88 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 89 | ok | observation_raw_source |  |
| 90 | ok | observation_raw_source |  |
| 91 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 92 | ok | observation |  |
| 93 | ok | observation_raw |  |
| 94 | ok | post_transition_richer_reobserve |  |
| 95 | fail | forward_predicate_rollback |  |
| 96 | warn | progress_clock |  |
| 97 | ok | step | app=WhatsApp screenshot=True |
| 98 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 99 | ok | observation_raw_source |  |
| 100 | ok | observation_raw_source |  |
| 101 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 102 | ok | observation |  |
| 103 | ok | observation_raw |  |
| 104 | ok | observation_raw |  |
| 105 | ok | observation_fused | LIST |
| 106 | ok | observation |  |
| 107 | ok | forward_task |  |
| 108 | ok | world_patch | Screen #1 |
| 109 | ok | fusion_conflicts |  |
| 110 | ok | goal_status |  |
| 111 | ok | decision_budget |  |
| 112 | ok | decision_engine |  |
| 113 | ok | planner_decision |  |
| 114 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 115 | warn | progress_clock |  |
| 116 | ok | step | app=WhatsApp screenshot=True |
| 117 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 118 | ok | observation_raw_source |  |
| 119 | ok | observation_raw_source |  |
| 120 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 121 | ok | observation |  |
| 122 | ok | observation_raw |  |
| 123 | ok | observation_raw |  |
| 124 | ok | observation_fused | LIST |
| 125 | ok | observation |  |
| 126 | ok | forward_task |  |
| 127 | ok | world_patch | Screen #1 |
| 128 | ok | fusion_conflicts |  |
| 129 | ok | goal_status |  |
| 130 | ok | decision_budget |  |
| 131 | ok | decision_engine |  |
| 132 | ok | planner_decision |  |
| 133 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 134 | warn | progress_clock |  |
| 135 | ok | step | app=WhatsApp screenshot=True |
| 136 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 137 | ok | observation_raw_source |  |
| 138 | ok | observation_raw_source |  |
| 139 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 140 | ok | observation |  |
| 141 | ok | observation_raw |  |
| 142 | ok | observation_raw |  |
| 143 | ok | observation_fused | LIST |
| 144 | ok | observation |  |
| 145 | ok | forward_task |  |
| 146 | ok | world_patch | Screen #1 |
| 147 | ok | fusion_conflicts |  |
| 148 | ok | goal_status |  |
| 149 | ok | decision_budget |  |
| 150 | ok | decision_engine |  |
| 151 | ok | planner_decision |  |
| 152 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 153 | fail | transition_attribution |  |
| 154 | warn | progress_clock |  |
| 155 | ok | step | app=WhatsApp screenshot=True |
| 156 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 157 | ok | observation_raw_source |  |
| 158 | ok | observation_raw_source |  |
| 159 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 160 | ok | observation |  |
| 161 | ok | observation_raw |  |
| 162 | ok | observation_raw |  |
| 163 | ok | observation_fused | LIST |
| 164 | ok | observation |  |
| 165 | ok | forward_task |  |
| 166 | ok | world_patch | Screen #1 |
| 167 | ok | goal_status |  |
| 168 | ok | decision_budget |  |
| 169 | ok | decision_engine |  |
| 170 | ok | planner_decision |  |
| 171 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 172 | ok | step | transition settle |
| 173 | ok | step | app=WhatsApp screenshot=True |
| 174 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 175 | ok | observation_raw_source |  |
| 176 | ok | observation_raw_source |  |
| 177 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 178 | ok | observation |  |
| 179 | ok | observation_raw |  |
| 180 | ok | observation_raw |  |
| 181 | ok | observation_fused | LIST |
| 182 | ok | step | transition poll |
| 183 | ok | perception_settled |  |
| 184 | ok | post_transition_settled_view | LIST |
| 185 | ok | post_observation |  |
| 186 | ok | post_world_patch |  |
| 187 | fail | transition_eval |  |
| 188 | ok | transition_attribution |  |
| 189 | fail | verification |  |
| 190 | ok | step | app=WhatsApp screenshot=True |
| 191 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 192 | ok | observation_raw_source |  |
| 193 | ok | observation_raw_source |  |
| 194 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 195 | ok | observation |  |
| 196 | ok | observation_raw |  |
| 197 | ok | post_transition_richer_reobserve |  |
| 198 | fail | forward_predicate_rollback |  |
| 199 | warn | progress_clock |  |
| 200 | ok | step | app=WhatsApp screenshot=True |
| 201 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 202 | ok | observation_raw_source |  |
| 203 | ok | observation_raw_source |  |
| 204 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 205 | ok | observation |  |
| 206 | ok | observation_raw |  |
| 207 | ok | observation_raw |  |
| 208 | ok | observation_fused | LIST |
| 209 | ok | observation |  |
| 210 | ok | forward_task |  |
| 211 | ok | world_patch | Screen #1 |
| 212 | ok | goal_status |  |
| 213 | ok | decision_budget |  |
| 214 | ok | decision_engine |  |
| 215 | ok | planner_decision |  |
| 216 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 217 | warn | progress_clock |  |
| 218 | ok | step | app=WhatsApp screenshot=True |
| 219 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 220 | ok | observation_raw_source |  |
| 221 | ok | observation_raw_source |  |
| 222 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 223 | ok | observation |  |
| 224 | ok | observation_raw |  |
| 225 | ok | observation_raw |  |
| 226 | ok | observation_fused | LIST |
| 227 | ok | observation |  |
| 228 | ok | forward_task |  |
| 229 | ok | world_patch | Screen #1 |
| 230 | ok | goal_status |  |
| 231 | ok | decision_budget |  |
| 232 | ok | decision_engine |  |
| 233 | ok | planner_decision |  |
| 234 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 235 | warn | progress_clock |  |
| 236 | ok | step | app=WhatsApp screenshot=True |
| 237 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 238 | ok | observation_raw_source |  |
| 239 | ok | observation_raw_source |  |
| 240 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 241 | ok | observation |  |
| 242 | ok | observation_raw |  |
| 243 | ok | observation_raw |  |
| 244 | ok | observation_fused | LIST |
| 245 | ok | observation |  |
| 246 | ok | forward_task |  |
| 247 | ok | world_patch | Screen #1 |
| 248 | ok | goal_status |  |
| 249 | ok | decision_budget |  |
| 250 | ok | decision_engine |  |
| 251 | ok | planner_decision |  |
| 252 | ok | step | low confidence (0.0) preferred=None among:  |
| 253 | warn | progress_clock |  |
| 254 | ok | step | app=WhatsApp screenshot=True |
| 255 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 256 | ok | observation_raw_source |  |
| 257 | ok | observation_raw_source |  |
| 258 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 259 | ok | observation |  |
| 260 | ok | observation_raw |  |
| 261 | ok | observation_raw |  |
| 262 | ok | observation_fused | LIST |
| 263 | ok | observation |  |
| 264 | ok | forward_task |  |
| 265 | ok | world_patch | Screen #1 |
| 266 | ok | goal_status |  |
| 267 | ok | decision_budget |  |
| 268 | ok | decision_engine |  |
| 269 | ok | planner_decision |  |
| 270 | ok | step | low confidence (0.0) preferred=None among:  |
| 271 | warn | progress_clock |  |
| 272 | ok | step | app=WhatsApp screenshot=True |
| 273 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 274 | ok | observation_raw_source |  |
| 275 | ok | observation_raw_source |  |
| 276 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 277 | ok | observation |  |
| 278 | ok | observation_raw |  |
| 279 | ok | observation_raw |  |
| 280 | ok | observation_fused | LIST |
| 281 | ok | observation |  |
| 282 | ok | forward_task |  |
| 283 | ok | world_patch | Screen #1 |
| 284 | ok | goal_status |  |
| 285 | ok | decision_budget |  |
| 286 | ok | decision_engine |  |
| 287 | ok | planner_decision |  |
| 288 | ok | step | low confidence (0.0) preferred=None among:  |
| 289 | warn | progress_clock |  |
| 290 | ok | step | app=WhatsApp screenshot=True |
| 291 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 292 | ok | observation_raw_source |  |
| 293 | ok | observation_raw_source |  |
| 294 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 295 | ok | observation |  |
| 296 | ok | observation_raw |  |
| 297 | ok | observation_raw |  |
| 298 | ok | observation_fused | LIST |
| 299 | ok | observation |  |
| 300 | ok | forward_task |  |
| 301 | ok | world_patch | Screen #1 |
| 302 | ok | goal_status |  |
| 303 | ok | decision_budget |  |
| 304 | ok | decision_engine |  |
| 305 | ok | planner_decision |  |
| 306 | ok | step | low confidence (0.0) preferred=None among:  |
| 307 | warn | progress_clock |  |
| 308 | ok | step | app=WhatsApp screenshot=True |
| 309 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 310 | ok | observation_raw_source |  |
| 311 | ok | observation_raw_source |  |
| 312 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 313 | ok | observation |  |
| 314 | ok | observation_raw |  |
| 315 | ok | observation_raw |  |
| 316 | ok | observation_fused | LIST |
| 317 | ok | observation |  |
| 318 | ok | forward_task |  |
| 319 | ok | world_patch | Screen #1 |
| 320 | ok | goal_status |  |
| 321 | ok | decision_budget |  |
| 322 | ok | decision_engine |  |
| 323 | ok | planner_decision |  |
| 324 | ok | step | low confidence (0.0) preferred=None among:  |
| 325 | warn | progress_clock |  |
| 326 | ok | step | app=WhatsApp screenshot=True |
| 327 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 328 | ok | observation_raw_source |  |
| 329 | ok | observation_raw_source |  |
| 330 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 331 | ok | observation |  |
| 332 | ok | observation_raw |  |
| 333 | ok | observation_raw |  |
| 334 | ok | observation_fused | LIST |
| 335 | ok | observation |  |
| 336 | ok | forward_task |  |
| 337 | ok | world_patch | Screen #1 |
| 338 | ok | goal_status |  |
| 339 | ok | decision_budget |  |
| 340 | ok | decision_engine |  |
| 341 | ok | planner_decision |  |
| 342 | ok | step | low confidence (0.0) preferred=None among:  |
| 343 | warn | progress_clock |  |
| 344 | ok | step | app=WhatsApp screenshot=True |
| 345 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 346 | ok | observation_raw_source |  |
| 347 | ok | observation_raw_source |  |
| 348 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 349 | ok | observation |  |
| 350 | ok | observation_raw |  |
| 351 | ok | observation_raw |  |
| 352 | ok | observation_fused | LIST |
| 353 | ok | observation |  |
| 354 | ok | forward_task |  |
| 355 | ok | world_patch | Screen #1 |
| 356 | ok | goal_status |  |
| 357 | ok | decision_budget |  |
| 358 | ok | decision_engine |  |
| 359 | ok | planner_decision |  |
| 360 | ok | step | low confidence (0.0) preferred=None among:  |
| 361 | warn | progress_clock |  |
| 362 | ok | step | app=WhatsApp screenshot=True |
| 363 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 364 | ok | observation_raw_source |  |
| 365 | ok | observation_raw_source |  |
| 366 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 367 | ok | observation |  |
| 368 | ok | observation_raw |  |
| 369 | ok | observation_raw |  |
| 370 | ok | observation_fused | LIST |
| 371 | ok | observation |  |
| 372 | ok | forward_task |  |
| 373 | ok | world_patch | Screen #1 |
| 374 | ok | goal_status |  |
| 375 | ok | decision_budget |  |
| 376 | ok | decision_engine |  |
| 377 | ok | planner_decision |  |
| 378 | ok | step | low confidence (0.0) preferred=None among:  |
| 379 | warn | progress_clock |  |
| 380 | ok | step | app=WhatsApp screenshot=True |
| 381 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 382 | ok | observation_raw_source |  |
| 383 | ok | observation_raw_source |  |
| 384 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 385 | ok | observation |  |
| 386 | ok | observation_raw |  |
| 387 | ok | observation_raw |  |
| 388 | ok | observation_fused | LIST |
| 389 | ok | observation |  |
| 390 | ok | forward_task |  |
| 391 | ok | world_patch | Screen #1 |
| 392 | ok | goal_status |  |
| 393 | ok | decision_budget |  |
| 394 | ok | decision_engine |  |
| 395 | ok | planner_decision |  |
| 396 | ok | step | low confidence (0.0) preferred=None among:  |
| 397 | warn | progress_clock |  |
| 398 | ok | step | app=WhatsApp screenshot=True |
| 399 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 400 | ok | observation_raw_source |  |
| 401 | ok | observation_raw_source |  |
| 402 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 403 | ok | observation |  |
| 404 | ok | observation_raw |  |
| 405 | ok | observation_raw |  |
| 406 | ok | observation_fused | LIST |
| 407 | ok | observation |  |
| 408 | ok | forward_task |  |
| 409 | ok | world_patch | Screen #1 |
| 410 | ok | goal_status |  |
| 411 | ok | decision_budget |  |
| 412 | ok | decision_engine |  |
| 413 | ok | planner_decision |  |
| 414 | ok | step | low confidence (0.0) preferred=None among:  |
| 415 | warn | progress_clock |  |
| 416 | ok | step | app=WhatsApp screenshot=True |
| 417 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 418 | ok | observation_raw_source |  |
| 419 | ok | observation_raw_source |  |
| 420 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 421 | ok | observation |  |
| 422 | ok | observation_raw |  |
| 423 | ok | observation_raw |  |
| 424 | ok | observation_fused | LIST |
| 425 | ok | observation |  |
| 426 | ok | forward_task |  |
| 427 | ok | world_patch | Screen #1 |
| 428 | ok | goal_status |  |
| 429 | ok | decision_budget |  |
| 430 | ok | decision_engine |  |
| 431 | ok | planner_decision |  |
| 432 | ok | step | low confidence (0.0) preferred=None among:  |
| 433 | warn | progress_clock |  |
| 434 | ok | step | app=WhatsApp screenshot=True |
| 435 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 436 | ok | observation_raw_source |  |
| 437 | ok | observation_raw_source |  |
| 438 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 439 | ok | observation |  |
| 440 | ok | observation_raw |  |
| 441 | ok | observation_raw |  |
| 442 | ok | observation_fused | LIST |
| 443 | ok | observation |  |
| 444 | ok | forward_task |  |
| 445 | ok | world_patch | Screen #1 |
| 446 | ok | goal_status |  |
| 447 | ok | decision_budget |  |
| 448 | ok | decision_engine |  |
| 449 | ok | planner_decision |  |
| 450 | ok | step | low confidence (0.0) preferred=None among:  |
| 451 | warn | progress_clock |  |
| 452 | ok | step | app=WhatsApp screenshot=True |
| 453 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 454 | ok | observation_raw_source |  |
| 455 | ok | observation_raw_source |  |
| 456 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 457 | ok | observation |  |
| 458 | ok | observation_raw |  |
| 459 | ok | observation_raw |  |
| 460 | ok | observation_fused | LIST |
| 461 | ok | observation |  |
| 462 | ok | forward_task |  |
| 463 | ok | world_patch | Screen #1 |
| 464 | ok | goal_status |  |
| 465 | ok | decision_budget |  |
| 466 | ok | decision_engine |  |
| 467 | ok | planner_decision |  |
| 468 | ok | step | low confidence (0.0) preferred=None among:  |
| 469 | warn | progress_clock |  |
| 470 | ok | step | app=WhatsApp screenshot=True |
| 471 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 472 | ok | observation_raw_source |  |
| 473 | ok | observation_raw_source |  |
| 474 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 475 | ok | observation |  |
| 476 | ok | observation_raw |  |
| 477 | ok | observation_raw |  |
| 478 | ok | observation_fused | LIST |
| 479 | ok | observation |  |
| 480 | ok | forward_task |  |
| 481 | ok | world_patch | Screen #1 |
| 482 | ok | goal_status |  |
| 483 | ok | decision_budget |  |
| 484 | ok | decision_engine |  |
| 485 | ok | planner_decision |  |
| 486 | ok | step | low confidence (0.0) preferred=None among:  |
| 487 | warn | progress_clock |  |
| 488 | ok | step | app=WhatsApp screenshot=True |
| 489 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 490 | ok | observation_raw_source |  |
| 491 | ok | observation_raw_source |  |
| 492 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 493 | ok | observation |  |
| 494 | ok | observation_raw |  |
| 495 | ok | observation_raw |  |
| 496 | ok | observation_fused | LIST |
| 497 | ok | observation |  |
| 498 | ok | forward_task |  |
| 499 | ok | world_patch | Screen #1 |
| 500 | ok | goal_status |  |
| 501 | ok | decision_budget |  |
| 502 | ok | decision_engine |  |
| 503 | ok | planner_decision |  |
| 504 | ok | step | low confidence (0.0) preferred=None among:  |
| 505 | warn | progress_clock |  |
| 506 | ok | step | app=WhatsApp screenshot=True |
| 507 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 508 | ok | observation_raw_source |  |
| 509 | ok | observation_raw_source |  |
| 510 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 511 | ok | observation |  |
| 512 | ok | observation_raw |  |
| 513 | ok | observation_raw |  |
| 514 | ok | observation_fused | LIST |
| 515 | ok | observation |  |
| 516 | ok | forward_task |  |
| 517 | ok | world_patch | Screen #1 |
| 518 | ok | goal_status |  |
| 519 | ok | decision_budget |  |
| 520 | ok | decision_engine |  |
| 521 | ok | planner_decision |  |
| 522 | ok | step | low confidence (0.0) preferred=None among:  |
| 523 | warn | progress_clock |  |
| 524 | ok | step | app=WhatsApp screenshot=True |
| 525 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 526 | ok | observation_raw_source |  |
| 527 | ok | observation_raw_source |  |
| 528 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 529 | ok | observation |  |
| 530 | ok | observation_raw |  |
| 531 | ok | observation_raw |  |
| 532 | ok | observation_fused | LIST |
| 533 | ok | observation |  |
| 534 | ok | forward_task |  |
| 535 | ok | world_patch | Screen #1 |
| 536 | ok | goal_status |  |
| 537 | ok | decision_budget |  |
| 538 | ok | decision_engine |  |
| 539 | ok | planner_decision |  |
| 540 | ok | step | low confidence (0.0) preferred=None among:  |
| 541 | warn | progress_clock |  |
| 542 | ok | step | app=WhatsApp screenshot=True |
| 543 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 544 | ok | observation_raw_source |  |
| 545 | ok | observation_raw_source |  |
| 546 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 547 | ok | observation |  |
| 548 | ok | observation_raw |  |
| 549 | ok | observation_raw |  |
| 550 | ok | observation_fused | LIST |
| 551 | ok | observation |  |
| 552 | ok | forward_task |  |
| 553 | ok | world_patch | Screen #1 |
| 554 | ok | goal_status |  |
| 555 | ok | decision_budget |  |
| 556 | ok | decision_engine |  |
| 557 | ok | planner_decision |  |
| 558 | ok | step | low confidence (0.0) preferred=None among:  |
| 559 | warn | progress_clock |  |
| 560 | ok | step | app=WhatsApp screenshot=True |
| 561 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 562 | ok | observation_raw_source |  |
| 563 | ok | observation_raw_source |  |
| 564 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 565 | ok | observation |  |
| 566 | ok | observation_raw |  |
| 567 | ok | observation_raw |  |
| 568 | ok | observation_fused | LIST |
| 569 | ok | observation |  |
| 570 | ok | forward_task |  |
| 571 | ok | world_patch | Screen #1 |
| 572 | ok | goal_status |  |
| 573 | ok | decision_budget |  |
| 574 | ok | decision_engine |  |
| 575 | ok | planner_decision |  |
| 576 | ok | step | low confidence (0.0) preferred=None among:  |
| 577 | warn | progress_clock |  |
| 578 | ok | step | app=WhatsApp screenshot=True |
| 579 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 580 | ok | observation_raw_source |  |
| 581 | ok | observation_raw_source |  |
| 582 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 583 | ok | observation |  |
| 584 | ok | observation_raw |  |
| 585 | ok | observation_raw |  |
| 586 | ok | observation_fused | LIST |
| 587 | ok | observation |  |
| 588 | ok | forward_task |  |
| 589 | ok | world_patch | Screen #1 |
| 590 | ok | goal_status |  |
| 591 | ok | decision_budget |  |
| 592 | ok | decision_engine |  |
| 593 | ok | planner_decision |  |
| 594 | ok | step | low confidence (0.0) preferred=None among:  |
| 595 | warn | progress_clock |  |
| 596 | ok | step | app=WhatsApp screenshot=True |
| 597 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 598 | ok | observation_raw_source |  |
| 599 | ok | observation_raw_source |  |
| 600 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 601 | ok | observation |  |
| 602 | ok | observation_raw |  |
| 603 | ok | observation_raw |  |
| 604 | ok | observation_fused | LIST |
| 605 | ok | observation |  |
| 606 | ok | forward_task |  |
| 607 | ok | world_patch | Screen #1 |
| 608 | ok | goal_status |  |
| 609 | ok | decision_budget |  |
| 610 | ok | decision_engine |  |
| 611 | ok | planner_decision |  |
| 612 | ok | step | low confidence (0.0) preferred=None among:  |
| 613 | warn | progress_clock |  |
| 614 | ok | step | app=WhatsApp screenshot=True |
| 615 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 616 | ok | observation_raw_source |  |
| 617 | ok | observation_raw_source |  |
| 618 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 619 | ok | observation |  |
| 620 | ok | observation_raw |  |
| 621 | ok | observation_raw |  |
| 622 | ok | observation_fused | LIST |
| 623 | ok | observation |  |
| 624 | ok | forward_task |  |
| 625 | ok | world_patch | Screen #1 |
| 626 | ok | goal_status |  |
| 627 | ok | decision_budget |  |
| 628 | ok | decision_engine |  |
| 629 | ok | planner_decision |  |
| 630 | ok | step | low confidence (0.0) preferred=None among:  |
| 631 | warn | progress_clock |  |
| 632 | ok | step | app=WhatsApp screenshot=True |
| 633 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 634 | ok | observation_raw_source |  |
| 635 | ok | observation_raw_source |  |
| 636 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 637 | ok | observation |  |
| 638 | ok | observation_raw |  |
| 639 | ok | observation_raw |  |
| 640 | ok | observation_fused | LIST |
| 641 | ok | observation |  |
| 642 | ok | forward_task |  |
| 643 | ok | world_patch | Screen #1 |
| 644 | ok | goal_status |  |
| 645 | ok | decision_budget |  |
| 646 | ok | decision_engine |  |
| 647 | ok | planner_decision |  |
| 648 | ok | step | low confidence (0.0) preferred=None among:  |
| 649 | warn | progress_clock |  |
| 650 | ok | step | app=WhatsApp screenshot=True |
| 651 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 652 | ok | observation_raw_source |  |
| 653 | ok | observation_raw_source |  |
| 654 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 655 | ok | observation |  |
| 656 | ok | observation_raw |  |
| 657 | ok | observation_raw |  |
| 658 | ok | observation_fused | LIST |
| 659 | ok | observation |  |
| 660 | ok | forward_task |  |
| 661 | ok | world_patch | Screen #1 |
| 662 | ok | goal_status |  |
| 663 | ok | decision_budget |  |
| 664 | ok | decision_engine |  |
| 665 | ok | planner_decision |  |
| 666 | ok | step | low confidence (0.0) preferred=None among:  |
| 667 | warn | progress_clock |  |
| 668 | ok | step | app=WhatsApp screenshot=True |
| 669 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 670 | ok | observation_raw_source |  |
| 671 | ok | observation_raw_source |  |
| 672 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 673 | ok | observation |  |
| 674 | ok | observation_raw |  |
| 675 | ok | observation_raw |  |
| 676 | ok | observation_fused | LIST |
| 677 | ok | observation |  |
| 678 | ok | forward_task |  |
| 679 | ok | world_patch | Screen #1 |
| 680 | ok | goal_status |  |
| 681 | ok | decision_budget |  |
| 682 | ok | decision_engine |  |
| 683 | ok | planner_decision |  |
| 684 | ok | step | low confidence (0.0) preferred=None among:  |
| 685 | warn | progress_clock |  |
| 686 | ok | step | app=WhatsApp screenshot=True |
| 687 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 688 | ok | observation_raw_source |  |
| 689 | ok | observation_raw_source |  |
| 690 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 691 | ok | observation |  |
| 692 | ok | observation_raw |  |
| 693 | ok | observation_raw |  |
| 694 | ok | observation_fused | LIST |
| 695 | ok | observation |  |
| 696 | ok | forward_task |  |
| 697 | ok | world_patch | Screen #1 |
| 698 | ok | goal_status |  |
| 699 | ok | decision_budget |  |
| 700 | ok | decision_engine |  |
| 701 | ok | planner_decision |  |
| 702 | ok | step | low confidence (0.0) preferred=None among:  |
| 703 | warn | progress_clock |  |
| 704 | ok | step | app=WhatsApp screenshot=True |
| 705 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 706 | ok | observation_raw_source |  |
| 707 | ok | observation_raw_source |  |
| 708 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 709 | ok | observation |  |
| 710 | ok | observation_raw |  |
| 711 | ok | observation_raw |  |
| 712 | ok | observation_fused | LIST |
| 713 | ok | observation |  |
| 714 | ok | forward_task |  |
| 715 | ok | world_patch | Screen #1 |
| 716 | ok | goal_status |  |
| 717 | ok | decision_budget |  |
| 718 | ok | decision_engine |  |
| 719 | ok | planner_decision |  |
| 720 | ok | step | low confidence (0.0) preferred=None among:  |
| 721 | warn | progress_clock |  |
| 722 | ok | step | app=WhatsApp screenshot=True |
| 723 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 724 | ok | observation_raw_source |  |
| 725 | ok | observation_raw_source |  |
| 726 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 727 | ok | observation |  |
| 728 | ok | observation_raw |  |
| 729 | ok | observation_raw |  |
| 730 | ok | observation_fused | LIST |
| 731 | ok | observation |  |
| 732 | ok | forward_task |  |
| 733 | ok | world_patch | Screen #1 |
| 734 | ok | goal_status |  |
| 735 | ok | decision_budget |  |
| 736 | ok | decision_engine |  |
| 737 | ok | planner_decision |  |
| 738 | ok | step | low confidence (0.0) preferred=None among:  |
| 739 | warn | progress_clock |  |
| 740 | ok | step | app=WhatsApp screenshot=True |
| 741 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 742 | ok | observation_raw_source |  |
| 743 | ok | observation_raw_source |  |
| 744 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 745 | ok | observation |  |
| 746 | ok | observation_raw |  |
| 747 | ok | observation_raw |  |
| 748 | ok | observation_fused | LIST |
| 749 | ok | observation |  |
| 750 | ok | forward_task |  |
| 751 | ok | world_patch | Screen #1 |
| 752 | ok | goal_status |  |
| 753 | ok | decision_budget |  |
| 754 | ok | decision_engine |  |
| 755 | ok | planner_decision |  |
| 756 | ok | step | low confidence (0.0) preferred=None among:  |
| 757 | warn | progress_clock |  |
| 758 | ok | step | app=WhatsApp screenshot=True |
| 759 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 760 | ok | observation_raw_source |  |
| 761 | ok | observation_raw_source |  |
| 762 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 763 | ok | observation |  |
| 764 | ok | observation_raw |  |
| 765 | ok | observation_raw |  |
| 766 | ok | observation_fused | LIST |
| 767 | ok | observation |  |
| 768 | ok | forward_task |  |
| 769 | ok | world_patch | Screen #1 |
| 770 | ok | goal_status |  |
| 771 | ok | decision_budget |  |
| 772 | ok | decision_engine |  |
| 773 | ok | planner_decision |  |
| 774 | ok | step | low confidence (0.0) preferred=None among:  |
| 775 | warn | progress_clock |  |
| 776 | ok | step | app=WhatsApp screenshot=True |
| 777 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 778 | ok | observation_raw_source |  |
| 779 | ok | observation_raw_source |  |
| 780 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 781 | ok | observation |  |
| 782 | ok | observation_raw |  |
| 783 | ok | observation_raw |  |
| 784 | ok | observation_fused | LIST |
| 785 | ok | observation |  |
| 786 | ok | forward_task |  |
| 787 | ok | world_patch | Screen #1 |
| 788 | ok | goal_status |  |
| 789 | ok | decision_budget |  |
| 790 | ok | decision_engine |  |
| 791 | ok | planner_decision |  |
| 792 | ok | step | low confidence (0.0) preferred=None among:  |
| 793 | warn | progress_clock |  |
| 794 | ok | step | app=WhatsApp screenshot=True |
| 795 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 796 | ok | observation_raw_source |  |
| 797 | ok | observation_raw_source |  |
| 798 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 799 | ok | observation |  |
| 800 | ok | observation_raw |  |
| 801 | ok | observation_raw |  |
| 802 | ok | observation_fused | LIST |
| 803 | ok | observation |  |
| 804 | ok | forward_task |  |
| 805 | ok | world_patch | Screen #1 |
| 806 | ok | goal_status |  |
| 807 | ok | decision_budget |  |
| 808 | ok | decision_engine |  |
| 809 | ok | planner_decision |  |
| 810 | ok | step | low confidence (0.0) preferred=None among:  |
| 811 | warn | progress_clock |  |
| 812 | ok | step | app=WhatsApp screenshot=True |
| 813 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 814 | ok | observation_raw_source |  |
| 815 | ok | observation_raw_source |  |
| 816 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 817 | ok | observation |  |
| 818 | ok | observation_raw |  |
| 819 | ok | observation_raw |  |
| 820 | ok | observation_fused | LIST |
| 821 | ok | observation |  |
| 822 | ok | forward_task |  |
| 823 | ok | world_patch | Screen #1 |
| 824 | ok | goal_status |  |
| 825 | ok | decision_budget |  |
| 826 | ok | decision_engine |  |
| 827 | ok | planner_decision |  |
| 828 | ok | step | low confidence (0.0) preferred=None among:  |
| 829 | warn | progress_clock |  |
| 830 | ok | step | app=WhatsApp screenshot=True |
| 831 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 832 | ok | observation_raw_source |  |
| 833 | ok | observation_raw_source |  |
| 834 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 835 | ok | observation |  |
| 836 | ok | observation_raw |  |
| 837 | ok | observation_raw |  |
| 838 | ok | observation_fused | LIST |
| 839 | ok | observation |  |
| 840 | ok | forward_task |  |
| 841 | ok | world_patch | Screen #1 |
| 842 | ok | goal_status |  |
| 843 | ok | decision_budget |  |
| 844 | ok | decision_engine |  |
| 845 | ok | planner_decision |  |
| 846 | ok | step | low confidence (0.0) preferred=None among:  |
| 847 | warn | progress_clock |  |
| 848 | ok | step | app=WhatsApp screenshot=True |
| 849 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 850 | ok | observation_raw_source |  |
| 851 | ok | observation_raw_source |  |
| 852 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 853 | ok | observation |  |
| 854 | ok | observation_raw |  |
| 855 | ok | observation_raw |  |
| 856 | ok | observation_fused | LIST |
| 857 | ok | observation |  |
| 858 | ok | forward_task |  |
| 859 | ok | world_patch | Screen #1 |
| 860 | ok | goal_status |  |
| 861 | ok | decision_budget |  |
| 862 | ok | decision_engine |  |
| 863 | ok | planner_decision |  |
| 864 | ok | step | low confidence (0.0) preferred=None among:  |
| 865 | warn | progress_clock |  |
| 866 | ok | step | app=WhatsApp screenshot=True |
| 867 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 868 | ok | observation_raw_source |  |
| 869 | ok | observation_raw_source |  |
| 870 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 871 | ok | observation |  |
| 872 | ok | observation_raw |  |
| 873 | ok | observation_raw |  |
| 874 | ok | observation_fused | LIST |
| 875 | ok | observation |  |
| 876 | ok | forward_task |  |
| 877 | ok | world_patch | Screen #1 |
| 878 | ok | goal_status |  |
| 879 | ok | decision_budget |  |
| 880 | ok | decision_engine |  |
| 881 | ok | planner_decision |  |
| 882 | ok | step | low confidence (0.0) preferred=None among:  |
| 883 | warn | progress_clock |  |
| 884 | ok | step | app=WhatsApp screenshot=True |
| 885 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 886 | ok | observation_raw_source |  |
| 887 | ok | observation_raw_source |  |
| 888 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 889 | ok | observation |  |
| 890 | ok | observation_raw |  |
| 891 | ok | observation_raw |  |
| 892 | ok | observation_fused | LIST |
| 893 | ok | observation |  |
| 894 | ok | forward_task |  |
| 895 | ok | world_patch | Screen #1 |
| 896 | ok | goal_status |  |
| 897 | ok | decision_budget |  |
| 898 | ok | decision_engine |  |
| 899 | ok | planner_decision |  |
| 900 | ok | step | low confidence (0.0) preferred=None among:  |
| 901 | warn | progress_clock |  |
| 902 | ok | step | app=WhatsApp screenshot=True |
| 903 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 904 | ok | observation_raw_source |  |
| 905 | ok | observation_raw_source |  |
| 906 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 907 | ok | observation |  |
| 908 | ok | observation_raw |  |
| 909 | ok | observation_raw |  |
| 910 | ok | observation_fused | LIST |
| 911 | ok | observation |  |
| 912 | ok | forward_task |  |
| 913 | ok | world_patch | Screen #1 |
| 914 | ok | goal_status |  |
| 915 | ok | decision_budget |  |
| 916 | ok | decision_engine |  |
| 917 | ok | planner_decision |  |
| 918 | ok | step | low confidence (0.0) preferred=None among:  |
| 919 | warn | progress_clock |  |
| 920 | ok | step | app=WhatsApp screenshot=True |
| 921 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 922 | ok | observation_raw_source |  |
| 923 | ok | observation_raw_source |  |
| 924 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 925 | ok | observation |  |
| 926 | ok | observation_raw |  |
| 927 | ok | observation_raw |  |
| 928 | ok | observation_fused | LIST |
| 929 | ok | observation |  |
| 930 | ok | forward_task |  |
| 931 | ok | world_patch | Screen #1 |
| 932 | ok | goal_status |  |
| 933 | ok | decision_budget |  |
| 934 | ok | decision_engine |  |
| 935 | ok | planner_decision |  |
| 936 | ok | step | low confidence (0.0) preferred=None among:  |
| 937 | warn | progress_clock |  |
| 938 | ok | step | app=WhatsApp screenshot=True |
| 939 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 940 | ok | observation_raw_source |  |
| 941 | ok | observation_raw_source |  |
| 942 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 943 | ok | observation |  |
| 944 | ok | observation_raw |  |
| 945 | ok | observation_raw |  |
| 946 | ok | observation_fused | LIST |
| 947 | ok | observation |  |
| 948 | ok | forward_task |  |
| 949 | ok | world_patch | Screen #1 |
| 950 | ok | goal_status |  |
| 951 | ok | decision_budget |  |
| 952 | ok | decision_engine |  |
| 953 | ok | planner_decision |  |
| 954 | ok | step | low confidence (0.0) preferred=None among:  |
| 955 | warn | progress_clock |  |
| 956 | ok | step | app=WhatsApp screenshot=True |
| 957 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 958 | ok | observation_raw_source |  |
| 959 | ok | observation_raw_source |  |
| 960 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 961 | ok | observation |  |
| 962 | ok | observation_raw |  |
| 963 | ok | observation_raw |  |
| 964 | ok | observation_fused | LIST |
| 965 | ok | observation |  |
| 966 | ok | forward_task |  |
| 967 | ok | world_patch | Screen #1 |
| 968 | ok | goal_status |  |
| 969 | ok | decision_budget |  |
| 970 | ok | decision_engine |  |
| 971 | ok | planner_decision |  |
| 972 | ok | step | low confidence (0.0) preferred=None among:  |
| 973 | warn | progress_clock |  |
| 974 | ok | step | app=WhatsApp screenshot=True |
| 975 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 976 | ok | observation_raw_source |  |
| 977 | ok | observation_raw_source |  |
| 978 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 979 | ok | observation |  |
| 980 | ok | observation_raw |  |
| 981 | ok | observation_raw |  |
| 982 | ok | observation_fused | LIST |
| 983 | ok | observation |  |
| 984 | ok | forward_task |  |
| 985 | ok | world_patch | Screen #1 |
| 986 | ok | goal_status |  |
| 987 | ok | decision_budget |  |
| 988 | ok | decision_engine |  |
| 989 | ok | planner_decision |  |
| 990 | ok | step | low confidence (0.0) preferred=None among:  |
| 991 | warn | progress_clock |  |
| 992 | ok | step | app=WhatsApp screenshot=True |
| 993 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 994 | ok | observation_raw_source |  |
| 995 | ok | observation_raw_source |  |
| 996 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 997 | ok | observation |  |
| 998 | ok | observation_raw |  |
| 999 | ok | observation_raw |  |
| 1000 | ok | observation_fused | LIST |
| 1001 | ok | observation |  |
| 1002 | ok | forward_task |  |
| 1003 | ok | world_patch | Screen #1 |
| 1004 | ok | goal_status |  |
| 1005 | ok | decision_budget |  |
| 1006 | ok | decision_engine |  |
| 1007 | ok | planner_decision |  |
| 1008 | ok | step | low confidence (0.0) preferred=None among:  |
| 1009 | warn | progress_clock |  |
| 1010 | ok | step | app=WhatsApp screenshot=True |
| 1011 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1012 | ok | observation_raw_source |  |
| 1013 | ok | observation_raw_source |  |
| 1014 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1015 | ok | observation |  |
| 1016 | ok | observation_raw |  |
| 1017 | ok | observation_raw |  |
| 1018 | ok | observation_fused | LIST |
| 1019 | ok | observation |  |
| 1020 | ok | forward_task |  |
| 1021 | ok | world_patch | Screen #1 |
| 1022 | ok | goal_status |  |
| 1023 | ok | decision_budget |  |
| 1024 | ok | decision_engine |  |
| 1025 | ok | planner_decision |  |
| 1026 | ok | step | low confidence (0.0) preferred=None among:  |
| 1027 | warn | progress_clock |  |
| 1028 | ok | step | app=WhatsApp screenshot=True |
| 1029 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1030 | ok | observation_raw_source |  |
| 1031 | ok | observation_raw_source |  |
| 1032 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1033 | ok | observation |  |
| 1034 | ok | observation_raw |  |
| 1035 | ok | observation_raw |  |
| 1036 | ok | observation_fused | LIST |
| 1037 | ok | observation |  |
| 1038 | ok | forward_task |  |
| 1039 | ok | world_patch | Screen #1 |
| 1040 | ok | goal_status |  |
| 1041 | ok | decision_budget |  |
| 1042 | ok | decision_engine |  |
| 1043 | ok | planner_decision |  |
| 1044 | ok | step | low confidence (0.0) preferred=None among:  |
| 1045 | warn | progress_clock |  |
| 1046 | ok | step | app=WhatsApp screenshot=True |
| 1047 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1048 | ok | observation_raw_source |  |
| 1049 | ok | observation_raw_source |  |
| 1050 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1051 | ok | observation |  |
| 1052 | ok | observation_raw |  |
| 1053 | ok | observation_raw |  |
| 1054 | ok | observation_fused | LIST |
| 1055 | ok | observation |  |
| 1056 | ok | forward_task |  |
| 1057 | ok | world_patch | Screen #1 |
| 1058 | ok | goal_status |  |
| 1059 | ok | decision_budget |  |
| 1060 | ok | decision_engine |  |
| 1061 | ok | planner_decision |  |
| 1062 | ok | step | low confidence (0.0) preferred=None among:  |
| 1063 | warn | progress_clock |  |
| 1064 | ok | step | app=WhatsApp screenshot=True |
| 1065 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1066 | ok | observation_raw_source |  |
| 1067 | ok | observation_raw_source |  |
| 1068 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1069 | ok | observation |  |
| 1070 | ok | observation_raw |  |
| 1071 | ok | observation_raw |  |
| 1072 | ok | observation_fused | LIST |
| 1073 | ok | observation |  |
| 1074 | ok | forward_task |  |
| 1075 | ok | world_patch | Screen #1 |
| 1076 | ok | goal_status |  |
| 1077 | ok | decision_budget |  |
| 1078 | ok | decision_engine |  |
| 1079 | ok | planner_decision |  |
| 1080 | ok | step | low confidence (0.0) preferred=None among:  |
| 1081 | warn | progress_clock |  |
| 1082 | ok | step | app=WhatsApp screenshot=True |
| 1083 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1084 | ok | observation_raw_source |  |
| 1085 | ok | observation_raw_source |  |
| 1086 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1087 | ok | observation |  |
| 1088 | ok | observation_raw |  |
| 1089 | ok | observation_raw |  |
| 1090 | ok | observation_fused | LIST |
| 1091 | ok | observation |  |
| 1092 | ok | forward_task |  |
| 1093 | ok | world_patch | Screen #1 |
| 1094 | ok | goal_status |  |
| 1095 | ok | decision_budget |  |
| 1096 | ok | decision_engine |  |
| 1097 | ok | planner_decision |  |
| 1098 | ok | step | low confidence (0.0) preferred=None among:  |
| 1099 | warn | progress_clock |  |
| 1100 | ok | step | app=WhatsApp screenshot=True |
| 1101 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1102 | ok | observation_raw_source |  |
| 1103 | ok | observation_raw_source |  |
| 1104 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1105 | ok | observation |  |
| 1106 | ok | observation_raw |  |
| 1107 | ok | observation_raw |  |
| 1108 | ok | observation_fused | LIST |
| 1109 | ok | observation |  |
| 1110 | ok | forward_task |  |
| 1111 | ok | world_patch | Screen #1 |
| 1112 | ok | goal_status |  |
| 1113 | ok | decision_budget |  |
| 1114 | ok | decision_engine |  |
| 1115 | ok | planner_decision |  |
| 1116 | ok | step | low confidence (0.0) preferred=None among:  |
| 1117 | warn | progress_clock |  |
| 1118 | ok | step | app=WhatsApp screenshot=True |
| 1119 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1120 | ok | observation_raw_source |  |
| 1121 | ok | observation_raw_source |  |
| 1122 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1123 | ok | observation |  |
| 1124 | ok | observation_raw |  |
| 1125 | ok | observation_raw |  |
| 1126 | ok | observation_fused | LIST |
| 1127 | ok | observation |  |
| 1128 | ok | forward_task |  |
| 1129 | ok | world_patch | Screen #1 |
| 1130 | ok | goal_status |  |
| 1131 | ok | decision_budget |  |
| 1132 | ok | decision_engine |  |
| 1133 | ok | planner_decision |  |
| 1134 | ok | step | low confidence (0.0) preferred=None among:  |
| 1135 | warn | progress_clock |  |
| 1136 | ok | step | app=WhatsApp screenshot=True |
| 1137 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1138 | ok | observation_raw_source |  |
| 1139 | ok | observation_raw_source |  |
| 1140 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1141 | ok | observation |  |
| 1142 | ok | observation_raw |  |
| 1143 | ok | observation_raw |  |
| 1144 | ok | observation_fused | LIST |
| 1145 | ok | observation |  |
| 1146 | ok | forward_task |  |
| 1147 | ok | world_patch | Screen #1 |
| 1148 | ok | goal_status |  |
| 1149 | ok | decision_budget |  |
| 1150 | ok | decision_engine |  |
| 1151 | ok | planner_decision |  |
| 1152 | ok | step | low confidence (0.0) preferred=None among:  |
| 1153 | warn | progress_clock |  |
| 1154 | ok | step | app=WhatsApp screenshot=True |
| 1155 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1156 | ok | observation_raw_source |  |
| 1157 | ok | observation_raw_source |  |
| 1158 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1159 | ok | observation |  |
| 1160 | ok | observation_raw |  |
| 1161 | ok | observation_raw |  |
| 1162 | ok | observation_fused | LIST |
| 1163 | ok | observation |  |
| 1164 | ok | forward_task |  |
| 1165 | ok | world_patch | Screen #1 |
| 1166 | ok | goal_status |  |
| 1167 | ok | decision_budget |  |
| 1168 | ok | decision_engine |  |
| 1169 | ok | planner_decision |  |
| 1170 | ok | step | low confidence (0.0) preferred=None among:  |
| 1171 | warn | progress_clock |  |
| 1172 | ok | step | app=WhatsApp screenshot=True |
| 1173 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1174 | ok | observation_raw_source |  |
| 1175 | ok | observation_raw_source |  |
| 1176 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1177 | ok | observation |  |
| 1178 | ok | observation_raw |  |
| 1179 | ok | observation_raw |  |
| 1180 | ok | observation_fused | LIST |
| 1181 | ok | observation |  |
| 1182 | ok | forward_task |  |
| 1183 | ok | world_patch | Screen #1 |
| 1184 | ok | goal_status |  |
| 1185 | ok | decision_budget |  |
| 1186 | ok | decision_engine |  |
| 1187 | ok | planner_decision |  |
| 1188 | ok | step | low confidence (0.0) preferred=None among:  |
| 1189 | warn | progress_clock |  |
| 1190 | ok | step | app=WhatsApp screenshot=True |
| 1191 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1192 | ok | observation_raw_source |  |
| 1193 | ok | observation_raw_source |  |
| 1194 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1195 | ok | observation |  |
| 1196 | ok | observation_raw |  |
| 1197 | ok | observation_raw |  |
| 1198 | ok | observation_fused | LIST |
| 1199 | ok | observation |  |
| 1200 | ok | forward_task |  |
| 1201 | ok | world_patch | Screen #1 |
| 1202 | ok | goal_status |  |
| 1203 | ok | decision_budget |  |
| 1204 | ok | decision_engine |  |
| 1205 | ok | planner_decision |  |
| 1206 | ok | step | low confidence (0.0) preferred=None among:  |
| 1207 | warn | progress_clock |  |
| 1208 | ok | step | app=WhatsApp screenshot=True |
| 1209 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1210 | ok | observation_raw_source |  |
| 1211 | ok | observation_raw_source |  |
| 1212 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1213 | ok | observation |  |
| 1214 | ok | observation_raw |  |
| 1215 | ok | observation_raw |  |
| 1216 | ok | observation_fused | LIST |
| 1217 | ok | observation |  |
| 1218 | ok | forward_task |  |
| 1219 | ok | world_patch | Screen #1 |
| 1220 | ok | goal_status |  |
| 1221 | ok | decision_budget |  |
| 1222 | ok | decision_engine |  |
| 1223 | ok | planner_decision |  |
| 1224 | ok | step | low confidence (0.0) preferred=None among:  |
| 1225 | warn | progress_clock |  |
| 1226 | ok | step | app=WhatsApp screenshot=True |
| 1227 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1228 | ok | observation_raw_source |  |
| 1229 | ok | observation_raw_source |  |
| 1230 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1231 | ok | observation |  |
| 1232 | ok | observation_raw |  |
| 1233 | ok | observation_raw |  |
| 1234 | ok | observation_fused | LIST |
| 1235 | ok | observation |  |
| 1236 | ok | forward_task |  |
| 1237 | ok | world_patch | Screen #1 |
| 1238 | ok | goal_status |  |
| 1239 | ok | decision_budget |  |
| 1240 | ok | decision_engine |  |
| 1241 | ok | planner_decision |  |
| 1242 | ok | step | low confidence (0.0) preferred=None among:  |
| 1243 | warn | progress_clock |  |
| 1244 | ok | step | app=WhatsApp screenshot=True |
| 1245 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1246 | ok | observation_raw_source |  |
| 1247 | ok | observation_raw_source |  |
| 1248 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1249 | ok | observation |  |
| 1250 | ok | observation_raw |  |
| 1251 | ok | observation_raw |  |
| 1252 | ok | observation_fused | LIST |
| 1253 | ok | observation |  |
| 1254 | ok | forward_task |  |
| 1255 | ok | world_patch | Screen #1 |
| 1256 | ok | goal_status |  |
| 1257 | ok | decision_budget |  |
| 1258 | ok | decision_engine |  |
| 1259 | ok | planner_decision |  |
| 1260 | ok | step | low confidence (0.0) preferred=None among:  |
| 1261 | warn | progress_clock |  |
| 1262 | ok | step | app=WhatsApp screenshot=True |
| 1263 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1264 | ok | observation_raw_source |  |
| 1265 | ok | observation_raw_source |  |
| 1266 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1267 | ok | observation |  |
| 1268 | ok | observation_raw |  |
| 1269 | ok | observation_raw |  |
| 1270 | ok | observation_fused | LIST |
| 1271 | ok | observation |  |
| 1272 | ok | forward_task |  |
| 1273 | ok | world_patch | Screen #1 |
| 1274 | ok | goal_status |  |
| 1275 | ok | decision_budget |  |
| 1276 | ok | decision_engine |  |
| 1277 | ok | planner_decision |  |
| 1278 | ok | step | low confidence (0.0) preferred=None among:  |
| 1279 | warn | progress_clock |  |
| 1280 | ok | step | app=WhatsApp screenshot=True |
| 1281 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1282 | ok | observation_raw_source |  |
| 1283 | ok | observation_raw_source |  |
| 1284 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1285 | ok | observation |  |
| 1286 | ok | observation_raw |  |
| 1287 | ok | observation_raw |  |
| 1288 | ok | observation_fused | LIST |
| 1289 | ok | observation |  |
| 1290 | ok | forward_task |  |
| 1291 | ok | world_patch | Screen #1 |
| 1292 | ok | goal_status |  |
| 1293 | ok | decision_budget |  |
| 1294 | ok | decision_engine |  |
| 1295 | ok | planner_decision |  |
| 1296 | ok | step | low confidence (0.0) preferred=None among:  |
| 1297 | warn | progress_clock |  |
| 1298 | ok | step | app=WhatsApp screenshot=True |
| 1299 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1300 | ok | observation_raw_source |  |
| 1301 | ok | observation_raw_source |  |
| 1302 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1303 | ok | observation |  |
| 1304 | ok | observation_raw |  |
| 1305 | ok | observation_raw |  |
| 1306 | ok | observation_fused | LIST |
| 1307 | ok | observation |  |
| 1308 | ok | forward_task |  |
| 1309 | ok | world_patch | Screen #1 |
| 1310 | ok | goal_status |  |
| 1311 | ok | decision_budget |  |
| 1312 | ok | decision_engine |  |
| 1313 | ok | planner_decision |  |
| 1314 | ok | step | low confidence (0.0) preferred=None among:  |
| 1315 | warn | progress_clock |  |
| 1316 | ok | step | app=WhatsApp screenshot=True |
| 1317 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1318 | ok | observation_raw_source |  |
| 1319 | ok | observation_raw_source |  |
| 1320 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1321 | ok | observation |  |
| 1322 | ok | observation_raw |  |
| 1323 | ok | observation_raw |  |
| 1324 | ok | observation_fused | LIST |
| 1325 | ok | observation |  |
| 1326 | ok | forward_task |  |
| 1327 | ok | world_patch | Screen #1 |
| 1328 | ok | goal_status |  |
| 1329 | ok | decision_budget |  |
| 1330 | ok | decision_engine |  |
| 1331 | ok | planner_decision |  |
| 1332 | ok | step | low confidence (0.0) preferred=None among:  |
| 1333 | warn | progress_clock |  |
| 1334 | ok | step | app=WhatsApp screenshot=True |
| 1335 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1336 | ok | observation_raw_source |  |
| 1337 | ok | observation_raw_source |  |
| 1338 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1339 | ok | observation |  |
| 1340 | ok | observation_raw |  |
| 1341 | ok | observation_raw |  |
| 1342 | ok | observation_fused | LIST |
| 1343 | ok | observation |  |
| 1344 | ok | forward_task |  |
| 1345 | ok | world_patch | Screen #1 |
| 1346 | ok | goal_status |  |
| 1347 | ok | decision_budget |  |
| 1348 | ok | decision_engine |  |
| 1349 | ok | planner_decision |  |
| 1350 | ok | step | low confidence (0.0) preferred=None among:  |
| 1351 | warn | progress_clock |  |
| 1352 | ok | step | app=WhatsApp screenshot=True |
| 1353 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1354 | ok | observation_raw_source |  |
| 1355 | ok | observation_raw_source |  |
| 1356 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1357 | ok | observation |  |
| 1358 | ok | observation_raw |  |
| 1359 | ok | observation_raw |  |
| 1360 | ok | observation_fused | LIST |
| 1361 | ok | observation |  |
| 1362 | ok | forward_task |  |
| 1363 | ok | world_patch | Screen #1 |
| 1364 | ok | goal_status |  |
| 1365 | ok | decision_budget |  |
| 1366 | ok | decision_engine |  |
| 1367 | ok | planner_decision |  |
| 1368 | ok | step | low confidence (0.0) preferred=None among:  |
| 1369 | warn | progress_clock |  |
| 1370 | ok | step | app=WhatsApp screenshot=True |
| 1371 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1372 | ok | observation_raw_source |  |
| 1373 | ok | observation_raw_source |  |
| 1374 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1375 | ok | observation |  |
| 1376 | ok | observation_raw |  |
| 1377 | ok | observation_raw |  |
| 1378 | ok | observation_fused | LIST |
| 1379 | ok | observation |  |
| 1380 | ok | forward_task |  |
| 1381 | ok | world_patch | Screen #1 |
| 1382 | ok | goal_status |  |
| 1383 | ok | decision_budget |  |
| 1384 | ok | decision_engine |  |
| 1385 | ok | planner_decision |  |
| 1386 | ok | step | low confidence (0.0) preferred=None among:  |
| 1387 | warn | progress_clock |  |
| 1388 | ok | step | app=WhatsApp screenshot=True |
| 1389 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1390 | ok | observation_raw_source |  |
| 1391 | ok | observation_raw_source |  |
| 1392 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1393 | ok | observation |  |
| 1394 | ok | observation_raw |  |
| 1395 | ok | observation_raw |  |
| 1396 | ok | observation_fused | LIST |
| 1397 | ok | observation |  |
| 1398 | ok | forward_task |  |
| 1399 | ok | world_patch | Screen #1 |
| 1400 | ok | goal_status |  |
| 1401 | ok | decision_budget |  |
| 1402 | ok | decision_engine |  |
| 1403 | ok | planner_decision |  |
| 1404 | ok | step | low confidence (0.0) preferred=None among:  |
| 1405 | warn | progress_clock |  |
| 1406 | ok | step | app=WhatsApp screenshot=True |
| 1407 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1408 | ok | observation_raw_source |  |
| 1409 | ok | observation_raw_source |  |
| 1410 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1411 | ok | observation |  |
| 1412 | ok | observation_raw |  |
| 1413 | ok | observation_raw |  |
| 1414 | ok | observation_fused | LIST |
| 1415 | ok | observation |  |
| 1416 | ok | forward_task |  |
| 1417 | ok | world_patch | Screen #1 |
| 1418 | ok | goal_status |  |
| 1419 | ok | decision_budget |  |
| 1420 | ok | decision_engine |  |
| 1421 | ok | planner_decision |  |
| 1422 | ok | step | low confidence (0.0) preferred=None among:  |
| 1423 | warn | progress_clock |  |
| 1424 | ok | step | app=WhatsApp screenshot=True |
| 1425 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1426 | ok | observation_raw_source |  |
| 1427 | ok | observation_raw_source |  |
| 1428 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1429 | ok | observation |  |
| 1430 | ok | observation_raw |  |
| 1431 | ok | observation_raw |  |
| 1432 | ok | observation_fused | LIST |
| 1433 | ok | observation |  |
| 1434 | ok | forward_task |  |
| 1435 | ok | world_patch | Screen #1 |
| 1436 | ok | goal_status |  |
| 1437 | ok | decision_budget |  |
| 1438 | ok | decision_engine |  |
| 1439 | ok | planner_decision |  |
| 1440 | ok | step | low confidence (0.0) preferred=None among:  |
| 1441 | warn | progress_clock |  |
| 1442 | ok | step | app=WhatsApp screenshot=True |
| 1443 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1444 | ok | observation_raw_source |  |
| 1445 | ok | observation_raw_source |  |
| 1446 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1447 | ok | observation |  |
| 1448 | ok | observation_raw |  |
| 1449 | ok | observation_raw |  |
| 1450 | ok | observation_fused | LIST |
| 1451 | ok | observation |  |
| 1452 | ok | forward_task |  |
| 1453 | ok | world_patch | Screen #1 |
| 1454 | ok | goal_status |  |
| 1455 | ok | decision_budget |  |
| 1456 | ok | decision_engine |  |
| 1457 | ok | planner_decision |  |
| 1458 | ok | step | low confidence (0.0) preferred=None among:  |
| 1459 | warn | progress_clock |  |
| 1460 | ok | step | app=WhatsApp screenshot=True |
| 1461 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1462 | ok | observation_raw_source |  |
| 1463 | ok | observation_raw_source |  |
| 1464 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1465 | ok | observation |  |
| 1466 | ok | observation_raw |  |
| 1467 | ok | observation_raw |  |
| 1468 | ok | observation_fused | LIST |
| 1469 | ok | observation |  |
| 1470 | ok | forward_task |  |
| 1471 | ok | world_patch | Screen #1 |
| 1472 | ok | goal_status |  |
| 1473 | ok | decision_budget |  |
| 1474 | ok | decision_engine |  |
| 1475 | ok | planner_decision |  |
| 1476 | ok | step | low confidence (0.0) preferred=None among:  |
| 1477 | warn | progress_clock |  |
| 1478 | ok | step | app=WhatsApp screenshot=True |
| 1479 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1480 | ok | observation_raw_source |  |
| 1481 | ok | observation_raw_source |  |
| 1482 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1483 | ok | observation |  |
| 1484 | ok | observation_raw |  |
| 1485 | ok | observation_raw |  |
| 1486 | ok | observation_fused | LIST |
| 1487 | ok | observation |  |
| 1488 | ok | forward_task |  |
| 1489 | ok | world_patch | Screen #1 |
| 1490 | ok | goal_status |  |
| 1491 | ok | decision_budget |  |
| 1492 | ok | decision_engine |  |
| 1493 | ok | planner_decision |  |
| 1494 | ok | step | low confidence (0.0) preferred=None among:  |
| 1495 | warn | progress_clock |  |
| 1496 | ok | step | app=WhatsApp screenshot=True |
| 1497 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1498 | ok | observation_raw_source |  |
| 1499 | ok | observation_raw_source |  |
| 1500 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1501 | ok | observation |  |
| 1502 | ok | observation_raw |  |
| 1503 | ok | observation_raw |  |
| 1504 | ok | observation_fused | LIST |
| 1505 | ok | observation |  |
| 1506 | ok | forward_task |  |
| 1507 | ok | world_patch | Screen #1 |
| 1508 | ok | goal_status |  |
| 1509 | ok | decision_budget |  |
| 1510 | ok | decision_engine |  |
| 1511 | ok | planner_decision |  |
| 1512 | ok | step | low confidence (0.0) preferred=None among:  |
| 1513 | warn | progress_clock |  |
| 1514 | ok | step | app=WhatsApp screenshot=True |
| 1515 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1516 | ok | observation_raw_source |  |
| 1517 | ok | observation_raw_source |  |
| 1518 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1519 | ok | observation |  |
| 1520 | ok | observation_raw |  |
| 1521 | ok | observation_raw |  |
| 1522 | ok | observation_fused | LIST |
| 1523 | ok | observation |  |
| 1524 | ok | forward_task |  |
| 1525 | ok | world_patch | Screen #1 |
| 1526 | ok | goal_status |  |
| 1527 | ok | decision_budget |  |
| 1528 | ok | decision_engine |  |
| 1529 | ok | planner_decision |  |
| 1530 | ok | step | low confidence (0.0) preferred=None among:  |
| 1531 | warn | progress_clock |  |
| 1532 | ok | step | app=WhatsApp screenshot=True |
| 1533 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1534 | ok | observation_raw_source |  |
| 1535 | ok | observation_raw_source |  |
| 1536 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1537 | ok | observation |  |
| 1538 | ok | observation_raw |  |
| 1539 | ok | observation_raw |  |
| 1540 | ok | observation_fused | LIST |
| 1541 | ok | observation |  |
| 1542 | ok | forward_task |  |
| 1543 | ok | world_patch | Screen #1 |
| 1544 | ok | goal_status |  |
| 1545 | ok | decision_budget |  |
| 1546 | ok | decision_engine |  |
| 1547 | ok | planner_decision |  |
| 1548 | ok | step | low confidence (0.0) preferred=None among:  |
| 1549 | warn | progress_clock |  |
| 1550 | ok | step | app=WhatsApp screenshot=True |
| 1551 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1552 | ok | observation_raw_source |  |
| 1553 | ok | observation_raw_source |  |
| 1554 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1555 | ok | observation |  |
| 1556 | ok | observation_raw |  |
| 1557 | ok | observation_raw |  |
| 1558 | ok | observation_fused | LIST |
| 1559 | ok | observation |  |
| 1560 | ok | forward_task |  |
| 1561 | ok | world_patch | Screen #1 |
| 1562 | ok | goal_status |  |
| 1563 | ok | decision_budget |  |
| 1564 | ok | decision_engine |  |
| 1565 | ok | planner_decision |  |
| 1566 | ok | step | low confidence (0.0) preferred=None among:  |
| 1567 | warn | progress_clock |  |
| 1568 | ok | step | app=WhatsApp screenshot=True |
| 1569 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1570 | ok | observation_raw_source |  |
| 1571 | ok | observation_raw_source |  |
| 1572 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1573 | ok | observation |  |
| 1574 | ok | observation_raw |  |
| 1575 | ok | observation_raw |  |
| 1576 | ok | observation_fused | LIST |
| 1577 | ok | observation |  |
| 1578 | ok | forward_task |  |
| 1579 | ok | world_patch | Screen #1 |
| 1580 | ok | goal_status |  |
| 1581 | ok | decision_budget |  |
| 1582 | ok | decision_engine |  |
| 1583 | ok | planner_decision |  |
| 1584 | ok | step | low confidence (0.0) preferred=None among:  |
| 1585 | warn | progress_clock |  |
| 1586 | ok | step | app=WhatsApp screenshot=True |
| 1587 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1588 | ok | observation_raw_source |  |
| 1589 | ok | observation_raw_source |  |
| 1590 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1591 | ok | observation |  |
| 1592 | ok | observation_raw |  |
| 1593 | ok | observation_raw |  |
| 1594 | ok | observation_fused | LIST |
| 1595 | ok | observation |  |
| 1596 | ok | forward_task |  |
| 1597 | ok | world_patch | Screen #1 |
| 1598 | ok | goal_status |  |
| 1599 | ok | decision_budget |  |
| 1600 | ok | decision_engine |  |
| 1601 | ok | planner_decision |  |
| 1602 | ok | step | low confidence (0.0) preferred=None among:  |
| 1603 | warn | progress_clock |  |
| 1604 | ok | step | app=WhatsApp screenshot=True |
| 1605 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1606 | ok | observation_raw_source |  |
| 1607 | ok | observation_raw_source |  |
| 1608 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1609 | ok | observation |  |
| 1610 | ok | observation_raw |  |
| 1611 | ok | observation_raw |  |
| 1612 | ok | observation_fused | LIST |
| 1613 | ok | observation |  |
| 1614 | ok | forward_task |  |
| 1615 | ok | world_patch | Screen #1 |
| 1616 | ok | goal_status |  |
| 1617 | ok | decision_budget |  |
| 1618 | ok | decision_engine |  |
| 1619 | ok | planner_decision |  |
| 1620 | ok | step | low confidence (0.0) preferred=None among:  |
| 1621 | warn | progress_clock |  |
| 1622 | ok | step | app=WhatsApp screenshot=True |
| 1623 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1624 | ok | observation_raw_source |  |
| 1625 | ok | observation_raw_source |  |
| 1626 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1627 | ok | observation |  |
| 1628 | ok | observation_raw |  |
| 1629 | ok | observation_raw |  |
| 1630 | ok | observation_fused | LIST |
| 1631 | ok | observation |  |
| 1632 | ok | forward_task |  |
| 1633 | ok | world_patch | Screen #1 |
| 1634 | ok | goal_status |  |
| 1635 | ok | decision_budget |  |
| 1636 | ok | decision_engine |  |
| 1637 | ok | planner_decision |  |
| 1638 | ok | step | low confidence (0.0) preferred=None among:  |
| 1639 | warn | progress_clock |  |
| 1640 | ok | step | app=WhatsApp screenshot=True |
| 1641 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1642 | ok | observation_raw_source |  |
| 1643 | ok | observation_raw_source |  |
| 1644 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1645 | ok | observation |  |
| 1646 | ok | observation_raw |  |
| 1647 | ok | observation_raw |  |
| 1648 | ok | observation_fused | LIST |
| 1649 | ok | observation |  |
| 1650 | ok | forward_task |  |
| 1651 | ok | world_patch | Screen #1 |
| 1652 | ok | goal_status |  |
| 1653 | ok | decision_budget |  |
| 1654 | ok | decision_engine |  |
| 1655 | ok | planner_decision |  |
| 1656 | ok | step | low confidence (0.0) preferred=None among:  |
| 1657 | warn | progress_clock |  |
| 1658 | ok | step | app=WhatsApp screenshot=True |
| 1659 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1660 | ok | observation_raw_source |  |
| 1661 | ok | observation_raw_source |  |
| 1662 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1663 | ok | observation |  |
| 1664 | ok | observation_raw |  |
| 1665 | ok | observation_raw |  |
| 1666 | ok | observation_fused | LIST |
| 1667 | ok | observation |  |
| 1668 | ok | forward_task |  |
| 1669 | ok | world_patch | Screen #1 |
| 1670 | ok | goal_status |  |
| 1671 | ok | decision_budget |  |
| 1672 | ok | decision_engine |  |
| 1673 | ok | planner_decision |  |
| 1674 | ok | step | low confidence (0.0) preferred=None among:  |
| 1675 | warn | progress_clock |  |
| 1676 | ok | step | app=WhatsApp screenshot=True |
| 1677 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1678 | ok | observation_raw_source |  |
| 1679 | ok | observation_raw_source |  |
| 1680 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1681 | ok | observation |  |
| 1682 | ok | observation_raw |  |
| 1683 | ok | observation_raw |  |
| 1684 | ok | observation_fused | LIST |
| 1685 | ok | observation |  |
| 1686 | ok | forward_task |  |
| 1687 | ok | world_patch | Screen #1 |
| 1688 | ok | goal_status |  |
| 1689 | ok | decision_budget |  |
| 1690 | ok | decision_engine |  |
| 1691 | ok | planner_decision |  |
| 1692 | ok | step | low confidence (0.0) preferred=None among:  |
| 1693 | warn | progress_clock |  |
| 1694 | ok | step | app=WhatsApp screenshot=True |
| 1695 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1696 | ok | observation_raw_source |  |
| 1697 | ok | observation_raw_source |  |
| 1698 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1699 | ok | observation |  |
| 1700 | ok | observation_raw |  |
| 1701 | ok | observation_raw |  |
| 1702 | ok | observation_fused | LIST |
| 1703 | ok | observation |  |
| 1704 | ok | forward_task |  |
| 1705 | ok | world_patch | Screen #1 |
| 1706 | ok | goal_status |  |
| 1707 | ok | decision_budget |  |
| 1708 | ok | decision_engine |  |
| 1709 | ok | planner_decision |  |
| 1710 | ok | step | low confidence (0.0) preferred=None among:  |
| 1711 | warn | progress_clock |  |
| 1712 | ok | step | app=WhatsApp screenshot=True |
| 1713 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1714 | ok | observation_raw_source |  |
| 1715 | ok | observation_raw_source |  |
| 1716 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1717 | ok | observation |  |
| 1718 | ok | observation_raw |  |
| 1719 | ok | observation_raw |  |
| 1720 | ok | observation_fused | LIST |
| 1721 | ok | observation |  |
| 1722 | ok | forward_task |  |
| 1723 | ok | world_patch | Screen #1 |
| 1724 | ok | goal_status |  |
| 1725 | ok | decision_budget |  |
| 1726 | ok | decision_engine |  |
| 1727 | ok | planner_decision |  |
| 1728 | ok | step | low confidence (0.0) preferred=None among:  |
| 1729 | warn | progress_clock |  |
| 1730 | ok | step | app=WhatsApp screenshot=True |
| 1731 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1732 | ok | observation_raw_source |  |
| 1733 | ok | observation_raw_source |  |
| 1734 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1735 | ok | observation |  |
| 1736 | ok | observation_raw |  |
| 1737 | ok | observation_raw |  |
| 1738 | ok | observation_fused | LIST |
| 1739 | ok | observation |  |
| 1740 | ok | forward_task |  |
| 1741 | ok | world_patch | Screen #1 |
| 1742 | ok | goal_status |  |
| 1743 | ok | decision_budget |  |
| 1744 | ok | decision_engine |  |
| 1745 | ok | planner_decision |  |
| 1746 | ok | step | low confidence (0.0) preferred=None among:  |
| 1747 | warn | progress_clock |  |
| 1748 | ok | step | app=WhatsApp screenshot=True |
| 1749 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1750 | ok | observation_raw_source |  |
| 1751 | ok | observation_raw_source |  |
| 1752 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1753 | ok | observation |  |
| 1754 | ok | observation_raw |  |
| 1755 | ok | observation_raw |  |
| 1756 | ok | observation_fused | LIST |
| 1757 | ok | observation |  |
| 1758 | ok | forward_task |  |
| 1759 | ok | world_patch | Screen #1 |
| 1760 | ok | goal_status |  |
| 1761 | ok | decision_budget |  |
| 1762 | ok | decision_engine |  |
| 1763 | ok | planner_decision |  |
| 1764 | ok | step | low confidence (0.0) preferred=None among:  |
| 1765 | warn | progress_clock |  |
| 1766 | ok | step | app=WhatsApp screenshot=True |
| 1767 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1768 | ok | observation_raw_source |  |
| 1769 | ok | observation_raw_source |  |
| 1770 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1771 | ok | observation |  |
| 1772 | ok | observation_raw |  |
| 1773 | ok | observation_raw |  |
| 1774 | ok | observation_fused | LIST |
| 1775 | ok | observation |  |
| 1776 | ok | forward_task |  |
| 1777 | ok | world_patch | Screen #1 |
| 1778 | ok | goal_status |  |
| 1779 | ok | decision_budget |  |
| 1780 | ok | decision_engine |  |
| 1781 | ok | planner_decision |  |
| 1782 | ok | step | low confidence (0.0) preferred=None among:  |
| 1783 | warn | progress_clock |  |
| 1784 | ok | step | app=WhatsApp screenshot=True |
| 1785 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1786 | ok | observation_raw_source |  |
| 1787 | ok | observation_raw_source |  |
| 1788 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1789 | ok | observation |  |
| 1790 | ok | observation_raw |  |
| 1791 | ok | observation_raw |  |
| 1792 | ok | observation_fused | LIST |
| 1793 | ok | observation |  |
| 1794 | ok | forward_task |  |
| 1795 | ok | world_patch | Screen #1 |
| 1796 | ok | goal_status |  |
| 1797 | ok | decision_budget |  |
| 1798 | ok | decision_engine |  |
| 1799 | ok | planner_decision |  |
| 1800 | ok | step | low confidence (0.0) preferred=None among:  |
| 1801 | warn | progress_clock |  |
| 1802 | ok | step | app=WhatsApp screenshot=True |
| 1803 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1804 | ok | observation_raw_source |  |
| 1805 | ok | observation_raw_source |  |
| 1806 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1807 | ok | observation |  |
| 1808 | ok | observation_raw |  |
| 1809 | ok | observation_raw |  |
| 1810 | ok | observation_fused | LIST |
| 1811 | ok | observation |  |
| 1812 | ok | forward_task |  |
| 1813 | ok | world_patch | Screen #1 |
| 1814 | ok | goal_status |  |
| 1815 | ok | decision_budget |  |
| 1816 | ok | decision_engine |  |
| 1817 | ok | planner_decision |  |
| 1818 | ok | step | low confidence (0.0) preferred=None among:  |
| 1819 | warn | progress_clock |  |
| 1820 | ok | step | app=WhatsApp screenshot=True |
| 1821 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1822 | ok | observation_raw_source |  |
| 1823 | ok | observation_raw_source |  |
| 1824 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1825 | ok | observation |  |
| 1826 | ok | observation_raw |  |
| 1827 | ok | observation_raw |  |
| 1828 | ok | observation_fused | LIST |
| 1829 | ok | observation |  |
| 1830 | ok | forward_task |  |
| 1831 | ok | world_patch | Screen #1 |
| 1832 | ok | goal_status |  |
| 1833 | ok | decision_budget |  |
| 1834 | ok | decision_engine |  |
| 1835 | ok | planner_decision |  |
| 1836 | ok | step | low confidence (0.0) preferred=None among:  |
| 1837 | warn | progress_clock |  |
| 1838 | ok | step | app=WhatsApp screenshot=True |
| 1839 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1840 | ok | observation_raw_source |  |
| 1841 | ok | observation_raw_source |  |
| 1842 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1843 | ok | observation |  |
| 1844 | ok | observation_raw |  |
| 1845 | ok | observation_raw |  |
| 1846 | ok | observation_fused | LIST |
| 1847 | ok | observation |  |
| 1848 | ok | forward_task |  |
| 1849 | ok | world_patch | Screen #1 |
| 1850 | ok | goal_status |  |
| 1851 | ok | decision_budget |  |
| 1852 | ok | decision_engine |  |
| 1853 | ok | planner_decision |  |
| 1854 | ok | step | low confidence (0.0) preferred=None among:  |
| 1855 | warn | progress_clock |  |
| 1856 | ok | step | app=WhatsApp screenshot=True |
| 1857 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1858 | ok | observation_raw_source |  |
| 1859 | ok | observation_raw_source |  |
| 1860 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1861 | ok | observation |  |
| 1862 | ok | observation_raw |  |
| 1863 | ok | observation_raw |  |
| 1864 | ok | observation_fused | LIST |
| 1865 | ok | observation |  |
| 1866 | ok | forward_task |  |
| 1867 | ok | world_patch | Screen #1 |
| 1868 | ok | goal_status |  |
| 1869 | ok | decision_budget |  |
| 1870 | ok | decision_engine |  |
| 1871 | ok | planner_decision |  |
| 1872 | ok | step | low confidence (0.0) preferred=None among:  |
| 1873 | warn | progress_clock |  |
| 1874 | ok | step | app=WhatsApp screenshot=True |
| 1875 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1876 | ok | observation_raw_source |  |
| 1877 | ok | observation_raw_source |  |
| 1878 | ok | step | sources=['pyobjc_ax'] agreement=0.7 |
| 1879 | ok | observation |  |
| 1880 | ok | observation_raw |  |
| 1881 | ok | observation_raw |  |
| 1882 | ok | observation_fused | LIST |
| 1883 | ok | observation |  |
| 1884 | ok | forward_task |  |
| 1885 | ok | world_patch | Screen #1 |
| 1886 | ok | goal_status |  |
| 1887 | ok | decision_budget |  |
| 1888 | ok | decision_engine |  |
| 1889 | ok | planner_decision |  |
| 1890 | ok | step | low confidence (0.0) preferred=None among:  |
| 1891 | ok | world_summary |  |
| 1892 | fail | check | fail |
| 1893 | fail | run_end | closed_loop ok=False reason='Maximum step count reached' iterations=100 |

## Failures

- seq=5 `check`: {"ts": 1785495667.822109, "run_elapsed_s": 0.545696, "run_elapsed_ms": 546, "seq": 5, "run_id": "wa-forward-live-1785495667", "kind": "check", "status": "fail", "name": "ghost_cli_installed", "expecte
- seq=48 `execution`: {"ts": 1785495848.274598, "run_elapsed_s": 180.998186, "run_elapsed_ms": 180998, "seq": 48, "run_id": "wa-forward-live-1785495667", "kind": "execution", "status": "fail", "ok": false, "backend": "ax",
- seq=49 `transition_attribution`: {"ts": 1785495848.275841, "run_elapsed_s": 180.99943, "run_elapsed_ms": 180999, "seq": 49, "run_id": "wa-forward-live-1785495667", "kind": "transition_attribution", "status": "fail", "action_family": 
- seq=84 `transition_eval`: {"ts": 1785495935.0648608, "run_elapsed_s": 267.788451, "run_elapsed_ms": 267788, "seq": 84, "run_id": "wa-forward-live-1785495667", "kind": "transition_eval", "status": "fail", "attempt": {"before_wo
- seq=86 `verification`: {"ts": 1785495935.065212, "run_elapsed_s": 267.788802, "run_elapsed_ms": 267789, "seq": 86, "run_id": "wa-forward-live-1785495667", "kind": "verification", "status": "fail", "passed": false, "reason":
- seq=95 `forward_predicate_rollback`: {"ts": 1785495958.583638, "run_elapsed_s": 291.307228, "run_elapsed_ms": 291307, "seq": 95, "run_id": "wa-forward-live-1785495667", "kind": "forward_predicate_rollback", "status": "fail", "expected": 
- seq=152 `execution`: {"ts": 1785496080.81014, "run_elapsed_s": 413.597417, "run_elapsed_ms": 413597, "seq": 152, "run_id": "wa-forward-live-1785495667", "kind": "execution", "status": "fail", "ok": false, "backend": "ax",
- seq=153 `transition_attribution`: {"ts": 1785496080.812226, "run_elapsed_s": 413.599505, "run_elapsed_ms": 413600, "seq": 153, "run_id": "wa-forward-live-1785495667", "kind": "transition_attribution", "status": "fail", "action_family"
- seq=187 `transition_eval`: {"ts": 1785496136.229297, "run_elapsed_s": 469.017141, "run_elapsed_ms": 469017, "seq": 187, "run_id": "wa-forward-live-1785495667", "kind": "transition_eval", "status": "fail", "attempt": {"before_wo
- seq=189 `verification`: {"ts": 1785496136.229532, "run_elapsed_s": 469.017376, "run_elapsed_ms": 469017, "seq": 189, "run_id": "wa-forward-live-1785495667", "kind": "verification", "status": "fail", "passed": false, "reason"
- seq=198 `forward_predicate_rollback`: {"ts": 1785496138.384732, "run_elapsed_s": 471.172598, "run_elapsed_ms": 471173, "seq": 198, "run_id": "wa-forward-live-1785495667", "kind": "forward_predicate_rollback", "status": "fail", "expected":
- seq=1892 `check`: {"ts": 1785496537.8779972, "run_elapsed_s": 870.669919, "run_elapsed_ms": 870670, "seq": 1892, "run_id": "wa-forward-live-1785495667", "kind": "check", "status": "fail", "name": "forward_task", "expec
- seq=1893 `run_end`: {"ts": 1785496537.8780532, "run_elapsed_s": 870.669974, "run_elapsed_ms": 870670, "seq": 1893, "run_id": "wa-forward-live-1785495667", "kind": "run_end", "status": "fail", "ok": false, "detail": "clos
