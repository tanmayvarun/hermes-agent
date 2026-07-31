# Run log — `wa-forward-live-1785219845`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260728_115404.jsonl`
- Events: 2582

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
| 14 | ok | step | attempt 1: leaving open="{'entity_id': 55, 'role': 'AXButton', 'label': 'Exit WhatsApp'}" toward chat list |
| 15 | ok | step | after preclear list |
| 16 | ok | step | app=WhatsApp screenshot=True |
| 17 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 18 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 19 | ok | observation |  |
| 20 | ok | world_patch | dialog |
| 21 | ok | step | attempt 2: leaving open='Exit WhatsApp' toward chat list |
| 22 | ok | step | after preclear list |
| 23 | ok | step | app=WhatsApp screenshot=True |
| 24 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 25 | ok | step | fallback=pyobjc_ax |
| 26 | ok | step | nodes=1 elapsed=0.00s |
| 27 | ok | observation |  |
| 28 | ok | world_patch | dialog |
| 29 | ok | step | closed-loop goal=find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 30 | ok | loop_budget |  |
| 31 | ok | step | app=WhatsApp screenshot=True |
| 32 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 33 | ok | step | fallback=pyobjc_ax |
| 34 | ok | step | nodes=1 elapsed=0.00s |
| 35 | ok | observation |  |
| 36 | ok | observation |  |
| 37 | ok | storage_cleanup |  |
| 38 | ok | step | storage pressure cleanup |
| 39 | ok | step | app=WhatsApp screenshot=True |
| 40 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 41 | ok | step | fallback=pyobjc_ax |
| 42 | ok | step | nodes=1 elapsed=0.00s |
| 43 | ok | observation |  |
| 44 | ok | observation |  |
| 45 | ok | forward_task |  |
| 46 | ok | world_patch | dialog |
| 47 | ok | goal_status |  |
| 48 | ok | decision_engine |  |
| 49 | ok | planner_decision |  |
| 50 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 51 | ok | step | transition settle |
| 52 | ok | step | app=WhatsApp screenshot=True |
| 53 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 54 | ok | step | fallback=pyobjc_ax |
| 55 | ok | step | nodes=1 elapsed=0.00s |
| 56 | ok | observation |  |
| 57 | ok | step | transition poll |
| 58 | ok | step | app=WhatsApp screenshot=True |
| 59 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 60 | ok | step | fallback=pyobjc_ax |
| 61 | ok | step | nodes=1 elapsed=0.00s |
| 62 | ok | observation |  |
| 63 | ok | step | transition poll |
| 64 | ok | step | app=WhatsApp screenshot=True |
| 65 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 66 | ok | step | fallback=pyobjc_ax |
| 67 | ok | step | nodes=1 elapsed=0.00s |
| 68 | ok | observation |  |
| 69 | ok | step | transition poll |
| 70 | ok | step | app=WhatsApp screenshot=True |
| 71 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 72 | ok | step | fallback=pyobjc_ax |
| 73 | ok | step | nodes=1 elapsed=0.00s |
| 74 | ok | observation |  |
| 75 | ok | step | transition poll |
| 76 | ok | perception_retry |  |
| 77 | ok | step | perception retry (fusion_agreement_low) |
| 78 | ok | step | app=WhatsApp screenshot=True |
| 79 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 80 | ok | step | fallback=pyobjc_ax |
| 81 | ok | step | nodes=1 elapsed=0.00s |
| 82 | ok | observation |  |
| 83 | fail | perception_unsettled |  |
| 84 | ok | post_observation |  |
| 85 | ok | post_world_patch |  |
| 86 | fail | transition_eval |  |
| 87 | ok | transition_attribution |  |
| 88 | fail | verification |  |
| 89 | ok | step | app=WhatsApp screenshot=True |
| 90 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 91 | ok | step | fallback=pyobjc_ax |
| 92 | ok | step | nodes=1 elapsed=0.00s |
| 93 | ok | observation |  |
| 94 | ok | post_transition_richer_reobserve |  |
| 95 | fail | forward_predicate_rollback |  |
| 96 | ok | step | app=WhatsApp screenshot=True |
| 97 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 98 | ok | step | fallback=pyobjc_ax |
| 99 | ok | step | nodes=1 elapsed=0.00s |
| 100 | ok | observation |  |
| 101 | ok | observation |  |
| 102 | ok | forward_task |  |
| 103 | ok | world_patch | dialog |
| 104 | ok | goal_status |  |
| 105 | ok | decision_engine |  |
| 106 | ok | planner_decision |  |
| 107 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 108 | ok | step | app=WhatsApp screenshot=True |
| 109 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 110 | ok | step | fallback=pyobjc_ax |
| 111 | ok | step | nodes=1 elapsed=0.00s |
| 112 | ok | observation |  |
| 113 | ok | observation |  |
| 114 | ok | forward_task |  |
| 115 | ok | world_patch | dialog |
| 116 | ok | goal_status |  |
| 117 | ok | decision_engine |  |
| 118 | ok | planner_decision |  |
| 119 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 120 | ok | step | app=WhatsApp screenshot=True |
| 121 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 122 | ok | step | fallback=pyobjc_ax |
| 123 | ok | step | nodes=1 elapsed=0.00s |
| 124 | ok | observation |  |
| 125 | ok | observation |  |
| 126 | ok | forward_task |  |
| 127 | ok | world_patch | dialog |
| 128 | ok | goal_status |  |
| 129 | ok | decision_engine |  |
| 130 | ok | planner_decision |  |
| 131 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 132 | ok | step | transition settle |
| 133 | ok | step | app=WhatsApp screenshot=True |
| 134 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 135 | ok | step | fallback=pyobjc_ax |
| 136 | ok | step | nodes=1 elapsed=0.00s |
| 137 | ok | observation |  |
| 138 | ok | step | transition poll |
| 139 | ok | step | app=WhatsApp screenshot=True |
| 140 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 141 | ok | step | fallback=pyobjc_ax |
| 142 | ok | step | nodes=1 elapsed=0.00s |
| 143 | ok | observation |  |
| 144 | ok | step | transition poll |
| 145 | ok | step | app=WhatsApp screenshot=True |
| 146 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 147 | ok | step | fallback=pyobjc_ax |
| 148 | ok | step | nodes=1 elapsed=0.00s |
| 149 | ok | observation |  |
| 150 | ok | step | transition poll |
| 151 | ok | step | app=WhatsApp screenshot=True |
| 152 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 153 | ok | step | fallback=pyobjc_ax |
| 154 | ok | step | nodes=1 elapsed=0.00s |
| 155 | ok | observation |  |
| 156 | ok | step | transition poll |
| 157 | ok | perception_retry |  |
| 158 | ok | step | perception retry (fusion_agreement_low) |
| 159 | ok | step | app=WhatsApp screenshot=True |
| 160 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 161 | ok | step | fallback=pyobjc_ax |
| 162 | ok | step | nodes=1 elapsed=0.00s |
| 163 | ok | observation |  |
| 164 | fail | perception_unsettled |  |
| 165 | ok | post_observation |  |
| 166 | ok | post_world_patch |  |
| 167 | fail | transition_eval |  |
| 168 | ok | transition_attribution |  |
| 169 | fail | verification |  |
| 170 | ok | step | app=WhatsApp screenshot=True |
| 171 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 172 | ok | step | fallback=pyobjc_ax |
| 173 | ok | step | nodes=1 elapsed=0.00s |
| 174 | ok | observation |  |
| 175 | ok | post_transition_richer_reobserve |  |
| 176 | fail | forward_predicate_rollback |  |
| 177 | ok | step | app=WhatsApp screenshot=True |
| 178 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 179 | ok | step | fallback=pyobjc_ax |
| 180 | ok | step | nodes=1 elapsed=0.00s |
| 181 | ok | observation |  |
| 182 | ok | observation |  |
| 183 | ok | forward_task |  |
| 184 | ok | world_patch | dialog |
| 185 | ok | goal_status |  |
| 186 | ok | decision_engine |  |
| 187 | ok | planner_decision |  |
| 188 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 189 | ok | step | app=WhatsApp screenshot=True |
| 190 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 191 | ok | step | fallback=pyobjc_ax |
| 192 | ok | step | nodes=1 elapsed=0.00s |
| 193 | ok | observation |  |
| 194 | ok | observation |  |
| 195 | ok | forward_task |  |
| 196 | ok | world_patch | dialog |
| 197 | ok | goal_status |  |
| 198 | ok | decision_engine |  |
| 199 | ok | planner_decision |  |
| 200 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 201 | ok | step | app=WhatsApp screenshot=True |
| 202 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 203 | ok | step | fallback=pyobjc_ax |
| 204 | ok | step | nodes=1 elapsed=0.00s |
| 205 | ok | observation |  |
| 206 | ok | observation |  |
| 207 | ok | forward_task |  |
| 208 | ok | world_patch | dialog |
| 209 | ok | goal_status |  |
| 210 | ok | decision_engine |  |
| 211 | ok | planner_decision |  |
| 212 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 213 | ok | step | transition settle |
| 214 | ok | step | app=WhatsApp screenshot=True |
| 215 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 216 | ok | step | fallback=pyobjc_ax |
| 217 | ok | step | nodes=1 elapsed=0.00s |
| 218 | ok | observation |  |
| 219 | ok | step | transition poll |
| 220 | ok | step | app=WhatsApp screenshot=True |
| 221 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 222 | ok | step | fallback=pyobjc_ax |
| 223 | ok | step | nodes=1 elapsed=0.00s |
| 224 | ok | observation |  |
| 225 | ok | step | transition poll |
| 226 | ok | step | app=WhatsApp screenshot=True |
| 227 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 228 | ok | step | fallback=pyobjc_ax |
| 229 | ok | step | nodes=1 elapsed=0.00s |
| 230 | ok | observation |  |
| 231 | ok | step | transition poll |
| 232 | ok | step | app=WhatsApp screenshot=True |
| 233 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 234 | ok | step | fallback=pyobjc_ax |
| 235 | ok | step | nodes=1 elapsed=0.00s |
| 236 | ok | observation |  |
| 237 | ok | step | transition poll |
| 238 | ok | perception_retry |  |
| 239 | ok | step | perception retry (fusion_agreement_low) |
| 240 | ok | step | app=WhatsApp screenshot=True |
| 241 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 242 | ok | step | fallback=pyobjc_ax |
| 243 | ok | step | nodes=1 elapsed=0.00s |
| 244 | ok | observation |  |
| 245 | fail | perception_unsettled |  |
| 246 | ok | post_observation |  |
| 247 | ok | post_world_patch |  |
| 248 | fail | transition_eval |  |
| 249 | ok | transition_attribution |  |
| 250 | fail | verification |  |
| 251 | ok | step | app=WhatsApp screenshot=True |
| 252 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 253 | ok | step | fallback=pyobjc_ax |
| 254 | ok | step | nodes=1 elapsed=0.00s |
| 255 | ok | observation |  |
| 256 | ok | post_transition_richer_reobserve |  |
| 257 | fail | forward_predicate_rollback |  |
| 258 | ok | step | app=WhatsApp screenshot=True |
| 259 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 260 | ok | step | fallback=pyobjc_ax |
| 261 | ok | step | nodes=1 elapsed=0.00s |
| 262 | ok | observation |  |
| 263 | ok | observation |  |
| 264 | ok | forward_task |  |
| 265 | ok | world_patch | dialog |
| 266 | ok | goal_status |  |
| 267 | ok | decision_engine |  |
| 268 | ok | planner_decision |  |
| 269 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 270 | ok | step | app=WhatsApp screenshot=True |
| 271 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 272 | ok | step | fallback=pyobjc_ax |
| 273 | ok | step | nodes=1 elapsed=0.00s |
| 274 | ok | observation |  |
| 275 | ok | observation |  |
| 276 | ok | forward_task |  |
| 277 | ok | world_patch | dialog |
| 278 | ok | goal_status |  |
| 279 | ok | decision_engine |  |
| 280 | ok | planner_decision |  |
| 281 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 282 | ok | step | app=WhatsApp screenshot=True |
| 283 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 284 | ok | step | fallback=pyobjc_ax |
| 285 | ok | step | nodes=1 elapsed=0.00s |
| 286 | ok | observation |  |
| 287 | ok | observation |  |
| 288 | ok | forward_task |  |
| 289 | ok | world_patch | dialog |
| 290 | ok | goal_status |  |
| 291 | ok | decision_engine |  |
| 292 | ok | planner_decision |  |
| 293 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 294 | ok | step | transition settle |
| 295 | ok | step | app=WhatsApp screenshot=True |
| 296 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 297 | ok | step | fallback=pyobjc_ax |
| 298 | ok | step | nodes=1 elapsed=0.00s |
| 299 | ok | observation |  |
| 300 | ok | step | transition poll |
| 301 | ok | step | app=WhatsApp screenshot=True |
| 302 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 303 | ok | step | fallback=pyobjc_ax |
| 304 | ok | step | nodes=1 elapsed=0.00s |
| 305 | ok | observation |  |
| 306 | ok | step | transition poll |
| 307 | ok | step | app=WhatsApp screenshot=True |
| 308 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 309 | ok | step | fallback=pyobjc_ax |
| 310 | ok | step | nodes=1 elapsed=0.00s |
| 311 | ok | observation |  |
| 312 | ok | step | transition poll |
| 313 | ok | step | app=WhatsApp screenshot=True |
| 314 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 315 | ok | step | fallback=pyobjc_ax |
| 316 | ok | step | nodes=1 elapsed=0.00s |
| 317 | ok | observation |  |
| 318 | ok | step | transition poll |
| 319 | ok | perception_retry |  |
| 320 | ok | step | perception retry (fusion_agreement_low) |
| 321 | ok | step | app=WhatsApp screenshot=True |
| 322 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 323 | ok | step | fallback=pyobjc_ax |
| 324 | ok | step | nodes=1 elapsed=0.00s |
| 325 | ok | observation |  |
| 326 | fail | perception_unsettled |  |
| 327 | ok | post_observation |  |
| 328 | ok | post_world_patch |  |
| 329 | fail | transition_eval |  |
| 330 | ok | transition_attribution |  |
| 331 | fail | verification |  |
| 332 | ok | step | app=WhatsApp screenshot=True |
| 333 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 334 | ok | step | fallback=pyobjc_ax |
| 335 | ok | step | nodes=1 elapsed=0.00s |
| 336 | ok | observation |  |
| 337 | ok | post_transition_richer_reobserve |  |
| 338 | fail | forward_predicate_rollback |  |
| 339 | ok | step | app=WhatsApp screenshot=True |
| 340 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 341 | ok | step | fallback=pyobjc_ax |
| 342 | ok | step | nodes=1 elapsed=0.00s |
| 343 | ok | observation |  |
| 344 | ok | observation |  |
| 345 | ok | forward_task |  |
| 346 | ok | world_patch | dialog |
| 347 | ok | goal_status |  |
| 348 | ok | decision_engine |  |
| 349 | ok | planner_decision |  |
| 350 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 351 | ok | step | app=WhatsApp screenshot=True |
| 352 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 353 | ok | step | fallback=pyobjc_ax |
| 354 | ok | step | nodes=1 elapsed=0.00s |
| 355 | ok | observation |  |
| 356 | ok | observation |  |
| 357 | ok | forward_task |  |
| 358 | ok | world_patch | dialog |
| 359 | ok | goal_status |  |
| 360 | ok | decision_engine |  |
| 361 | ok | planner_decision |  |
| 362 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 363 | ok | step | app=WhatsApp screenshot=True |
| 364 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 365 | ok | step | fallback=pyobjc_ax |
| 366 | ok | step | nodes=1 elapsed=0.00s |
| 367 | ok | observation |  |
| 368 | ok | observation |  |
| 369 | ok | forward_task |  |
| 370 | ok | world_patch | dialog |
| 371 | ok | goal_status |  |
| 372 | ok | decision_engine |  |
| 373 | ok | planner_decision |  |
| 374 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 375 | ok | step | transition settle |
| 376 | ok | step | app=WhatsApp screenshot=True |
| 377 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 378 | ok | step | fallback=pyobjc_ax |
| 379 | ok | step | nodes=1 elapsed=0.00s |
| 380 | ok | observation |  |
| 381 | ok | step | transition poll |
| 382 | ok | step | app=WhatsApp screenshot=True |
| 383 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 384 | ok | step | fallback=pyobjc_ax |
| 385 | ok | step | nodes=1 elapsed=0.00s |
| 386 | ok | observation |  |
| 387 | ok | step | transition poll |
| 388 | ok | step | app=WhatsApp screenshot=True |
| 389 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 390 | ok | step | fallback=pyobjc_ax |
| 391 | ok | step | nodes=1 elapsed=0.00s |
| 392 | ok | observation |  |
| 393 | ok | step | transition poll |
| 394 | ok | perception_retry |  |
| 395 | ok | step | perception retry (fusion_agreement_low) |
| 396 | ok | step | app=WhatsApp screenshot=True |
| 397 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 398 | ok | step | fallback=pyobjc_ax |
| 399 | ok | step | nodes=1 elapsed=0.00s |
| 400 | ok | observation |  |
| 401 | fail | perception_unsettled |  |
| 402 | ok | post_observation |  |
| 403 | ok | post_world_patch |  |
| 404 | fail | transition_eval |  |
| 405 | ok | transition_attribution |  |
| 406 | fail | verification |  |
| 407 | ok | step | app=WhatsApp screenshot=True |
| 408 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 409 | ok | step | fallback=pyobjc_ax |
| 410 | ok | step | nodes=1 elapsed=0.00s |
| 411 | ok | observation |  |
| 412 | ok | post_transition_richer_reobserve |  |
| 413 | fail | forward_predicate_rollback |  |
| 414 | ok | step | app=WhatsApp screenshot=True |
| 415 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 416 | ok | step | fallback=pyobjc_ax |
| 417 | ok | step | nodes=1 elapsed=0.00s |
| 418 | ok | observation |  |
| 419 | ok | observation |  |
| 420 | ok | forward_task |  |
| 421 | ok | world_patch | dialog |
| 422 | ok | goal_status |  |
| 423 | ok | decision_engine |  |
| 424 | ok | planner_decision |  |
| 425 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 426 | ok | step | app=WhatsApp screenshot=True |
| 427 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 428 | ok | step | fallback=pyobjc_ax |
| 429 | ok | step | nodes=1 elapsed=0.00s |
| 430 | ok | observation |  |
| 431 | ok | observation |  |
| 432 | ok | forward_task |  |
| 433 | ok | world_patch | dialog |
| 434 | ok | goal_status |  |
| 435 | ok | decision_engine |  |
| 436 | ok | planner_decision |  |
| 437 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 438 | ok | step | app=WhatsApp screenshot=True |
| 439 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 440 | ok | step | fallback=pyobjc_ax |
| 441 | ok | step | nodes=1 elapsed=0.00s |
| 442 | ok | observation |  |
| 443 | ok | observation |  |
| 444 | ok | forward_task |  |
| 445 | ok | world_patch | dialog |
| 446 | ok | goal_status |  |
| 447 | ok | decision_engine |  |
| 448 | ok | planner_decision |  |
| 449 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 450 | ok | step | transition settle |
| 451 | ok | step | app=WhatsApp screenshot=True |
| 452 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 453 | ok | step | fallback=pyobjc_ax |
| 454 | ok | step | nodes=1 elapsed=0.00s |
| 455 | ok | observation |  |
| 456 | ok | step | transition poll |
| 457 | ok | step | app=WhatsApp screenshot=True |
| 458 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 459 | ok | step | fallback=pyobjc_ax |
| 460 | ok | step | nodes=1 elapsed=0.00s |
| 461 | ok | observation |  |
| 462 | ok | step | transition poll |
| 463 | ok | step | app=WhatsApp screenshot=True |
| 464 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 465 | ok | step | fallback=pyobjc_ax |
| 466 | ok | step | nodes=1 elapsed=0.00s |
| 467 | ok | observation |  |
| 468 | ok | step | transition poll |
| 469 | ok | perception_retry |  |
| 470 | ok | step | perception retry (fusion_agreement_low) |
| 471 | ok | step | app=WhatsApp screenshot=True |
| 472 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 473 | ok | step | fallback=pyobjc_ax |
| 474 | ok | step | nodes=1 elapsed=0.00s |
| 475 | ok | observation |  |
| 476 | fail | perception_unsettled |  |
| 477 | ok | post_observation |  |
| 478 | ok | post_world_patch |  |
| 479 | fail | transition_eval |  |
| 480 | ok | transition_attribution |  |
| 481 | fail | verification |  |
| 482 | ok | step | app=WhatsApp screenshot=True |
| 483 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 484 | ok | step | fallback=pyobjc_ax |
| 485 | ok | step | nodes=1 elapsed=0.00s |
| 486 | ok | observation |  |
| 487 | ok | post_transition_richer_reobserve |  |
| 488 | fail | forward_predicate_rollback |  |
| 489 | ok | step | app=WhatsApp screenshot=True |
| 490 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 491 | ok | step | fallback=pyobjc_ax |
| 492 | ok | step | nodes=1 elapsed=0.00s |
| 493 | ok | observation |  |
| 494 | ok | observation |  |
| 495 | ok | forward_task |  |
| 496 | ok | world_patch | dialog |
| 497 | ok | goal_status |  |
| 498 | ok | decision_engine |  |
| 499 | ok | planner_decision |  |
| 500 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 501 | ok | step | app=WhatsApp screenshot=True |
| 502 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 503 | ok | step | fallback=pyobjc_ax |
| 504 | ok | step | nodes=1 elapsed=0.00s |
| 505 | ok | observation |  |
| 506 | ok | observation |  |
| 507 | ok | forward_task |  |
| 508 | ok | world_patch | dialog |
| 509 | ok | goal_status |  |
| 510 | ok | decision_engine |  |
| 511 | ok | planner_decision |  |
| 512 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 513 | ok | step | app=WhatsApp screenshot=True |
| 514 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 515 | ok | step | fallback=pyobjc_ax |
| 516 | ok | step | nodes=1 elapsed=0.00s |
| 517 | ok | observation |  |
| 518 | ok | observation |  |
| 519 | ok | forward_task |  |
| 520 | ok | world_patch | dialog |
| 521 | ok | goal_status |  |
| 522 | ok | decision_engine |  |
| 523 | ok | planner_decision |  |
| 524 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 525 | ok | step | transition settle |
| 526 | ok | step | app=WhatsApp screenshot=True |
| 527 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 528 | ok | step | fallback=pyobjc_ax |
| 529 | ok | step | nodes=1 elapsed=0.00s |
| 530 | ok | observation |  |
| 531 | ok | step | transition poll |
| 532 | ok | step | app=WhatsApp screenshot=True |
| 533 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 534 | ok | step | fallback=pyobjc_ax |
| 535 | ok | step | nodes=1 elapsed=0.00s |
| 536 | ok | observation |  |
| 537 | ok | step | transition poll |
| 538 | ok | step | app=WhatsApp screenshot=True |
| 539 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 540 | ok | step | fallback=pyobjc_ax |
| 541 | ok | step | nodes=1 elapsed=0.00s |
| 542 | ok | observation |  |
| 543 | ok | step | transition poll |
| 544 | ok | step | app=WhatsApp screenshot=True |
| 545 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 546 | ok | step | fallback=pyobjc_ax |
| 547 | ok | step | nodes=1 elapsed=0.00s |
| 548 | ok | observation |  |
| 549 | ok | step | transition poll |
| 550 | ok | perception_retry |  |
| 551 | ok | step | perception retry (fusion_agreement_low) |
| 552 | ok | step | app=WhatsApp screenshot=True |
| 553 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 554 | ok | step | fallback=pyobjc_ax |
| 555 | ok | step | nodes=1 elapsed=0.00s |
| 556 | ok | observation |  |
| 557 | fail | perception_unsettled |  |
| 558 | ok | post_observation |  |
| 559 | ok | post_world_patch |  |
| 560 | fail | transition_eval |  |
| 561 | ok | transition_attribution |  |
| 562 | fail | verification |  |
| 563 | ok | step | app=WhatsApp screenshot=True |
| 564 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 565 | ok | step | fallback=pyobjc_ax |
| 566 | ok | step | nodes=1 elapsed=0.00s |
| 567 | ok | observation |  |
| 568 | ok | post_transition_richer_reobserve |  |
| 569 | fail | forward_predicate_rollback |  |
| 570 | ok | step | app=WhatsApp screenshot=True |
| 571 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 572 | ok | step | fallback=pyobjc_ax |
| 573 | ok | step | nodes=1 elapsed=0.00s |
| 574 | ok | observation |  |
| 575 | ok | observation |  |
| 576 | ok | forward_task |  |
| 577 | ok | world_patch | dialog |
| 578 | ok | goal_status |  |
| 579 | ok | decision_engine |  |
| 580 | ok | planner_decision |  |
| 581 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 582 | ok | step | app=WhatsApp screenshot=True |
| 583 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 584 | ok | step | fallback=pyobjc_ax |
| 585 | ok | step | nodes=1 elapsed=0.00s |
| 586 | ok | observation |  |
| 587 | ok | observation |  |
| 588 | ok | forward_task |  |
| 589 | ok | world_patch | dialog |
| 590 | ok | goal_status |  |
| 591 | ok | decision_engine |  |
| 592 | ok | planner_decision |  |
| 593 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 594 | ok | step | app=WhatsApp screenshot=True |
| 595 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 596 | ok | step | fallback=pyobjc_ax |
| 597 | ok | step | nodes=1 elapsed=0.00s |
| 598 | ok | observation |  |
| 599 | ok | observation |  |
| 600 | ok | forward_task |  |
| 601 | ok | world_patch | dialog |
| 602 | ok | goal_status |  |
| 603 | ok | decision_engine |  |
| 604 | ok | planner_decision |  |
| 605 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 606 | ok | step | transition settle |
| 607 | ok | step | app=WhatsApp screenshot=True |
| 608 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 609 | ok | step | fallback=pyobjc_ax |
| 610 | ok | step | nodes=1 elapsed=0.00s |
| 611 | ok | observation |  |
| 612 | ok | step | transition poll |
| 613 | ok | step | app=WhatsApp screenshot=True |
| 614 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 615 | ok | step | fallback=pyobjc_ax |
| 616 | ok | step | nodes=1 elapsed=0.00s |
| 617 | ok | observation |  |
| 618 | ok | step | transition poll |
| 619 | ok | step | app=WhatsApp screenshot=True |
| 620 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 621 | ok | step | fallback=pyobjc_ax |
| 622 | ok | step | nodes=1 elapsed=0.00s |
| 623 | ok | observation |  |
| 624 | ok | step | transition poll |
| 625 | ok | perception_retry |  |
| 626 | ok | step | perception retry (fusion_agreement_low) |
| 627 | ok | step | app=WhatsApp screenshot=True |
| 628 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 629 | ok | step | fallback=pyobjc_ax |
| 630 | ok | step | nodes=1 elapsed=0.00s |
| 631 | ok | observation |  |
| 632 | fail | perception_unsettled |  |
| 633 | ok | post_observation |  |
| 634 | ok | post_world_patch |  |
| 635 | fail | transition_eval |  |
| 636 | ok | transition_attribution |  |
| 637 | fail | verification |  |
| 638 | ok | step | app=WhatsApp screenshot=True |
| 639 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 640 | ok | step | fallback=pyobjc_ax |
| 641 | ok | step | nodes=1 elapsed=0.00s |
| 642 | ok | observation |  |
| 643 | ok | post_transition_richer_reobserve |  |
| 644 | fail | forward_predicate_rollback |  |
| 645 | ok | step | app=WhatsApp screenshot=True |
| 646 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 647 | ok | step | fallback=pyobjc_ax |
| 648 | ok | step | nodes=1 elapsed=0.00s |
| 649 | ok | observation |  |
| 650 | ok | observation |  |
| 651 | ok | forward_task |  |
| 652 | ok | world_patch | dialog |
| 653 | ok | goal_status |  |
| 654 | ok | decision_engine |  |
| 655 | ok | planner_decision |  |
| 656 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 657 | ok | step | app=WhatsApp screenshot=True |
| 658 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 659 | ok | step | fallback=pyobjc_ax |
| 660 | ok | step | nodes=1 elapsed=0.00s |
| 661 | ok | observation |  |
| 662 | ok | observation |  |
| 663 | ok | forward_task |  |
| 664 | ok | world_patch | dialog |
| 665 | ok | goal_status |  |
| 666 | ok | decision_engine |  |
| 667 | ok | planner_decision |  |
| 668 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 669 | ok | step | app=WhatsApp screenshot=True |
| 670 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 671 | ok | step | fallback=pyobjc_ax |
| 672 | ok | step | nodes=1 elapsed=0.00s |
| 673 | ok | observation |  |
| 674 | ok | observation |  |
| 675 | ok | forward_task |  |
| 676 | ok | world_patch | dialog |
| 677 | ok | goal_status |  |
| 678 | ok | decision_engine |  |
| 679 | ok | planner_decision |  |
| 680 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 681 | ok | step | transition settle |
| 682 | ok | step | app=WhatsApp screenshot=True |
| 683 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 684 | ok | step | fallback=pyobjc_ax |
| 685 | ok | step | nodes=1 elapsed=0.00s |
| 686 | ok | observation |  |
| 687 | ok | step | transition poll |
| 688 | ok | step | app=WhatsApp screenshot=True |
| 689 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 690 | ok | step | fallback=pyobjc_ax |
| 691 | ok | step | nodes=1 elapsed=0.00s |
| 692 | ok | observation |  |
| 693 | ok | step | transition poll |
| 694 | ok | step | app=WhatsApp screenshot=True |
| 695 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 696 | ok | step | fallback=pyobjc_ax |
| 697 | ok | step | nodes=1 elapsed=0.00s |
| 698 | ok | observation |  |
| 699 | ok | step | transition poll |
| 700 | ok | perception_retry |  |
| 701 | ok | step | perception retry (fusion_agreement_low) |
| 702 | ok | step | app=WhatsApp screenshot=True |
| 703 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 704 | ok | step | fallback=pyobjc_ax |
| 705 | ok | step | nodes=1 elapsed=0.00s |
| 706 | ok | observation |  |
| 707 | fail | perception_unsettled |  |
| 708 | ok | post_observation |  |
| 709 | ok | post_world_patch |  |
| 710 | fail | transition_eval |  |
| 711 | ok | transition_attribution |  |
| 712 | fail | verification |  |
| 713 | ok | step | app=WhatsApp screenshot=True |
| 714 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 715 | ok | step | fallback=pyobjc_ax |
| 716 | ok | step | nodes=1 elapsed=0.00s |
| 717 | ok | observation |  |
| 718 | ok | post_transition_richer_reobserve |  |
| 719 | fail | forward_predicate_rollback |  |
| 720 | ok | step | app=WhatsApp screenshot=True |
| 721 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 722 | ok | step | fallback=pyobjc_ax |
| 723 | ok | step | nodes=1 elapsed=0.00s |
| 724 | ok | observation |  |
| 725 | ok | observation |  |
| 726 | ok | forward_task |  |
| 727 | ok | world_patch | dialog |
| 728 | ok | goal_status |  |
| 729 | ok | decision_engine |  |
| 730 | ok | planner_decision |  |
| 731 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 732 | ok | step | app=WhatsApp screenshot=True |
| 733 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 734 | ok | step | fallback=pyobjc_ax |
| 735 | ok | step | nodes=1 elapsed=0.00s |
| 736 | ok | observation |  |
| 737 | ok | observation |  |
| 738 | ok | forward_task |  |
| 739 | ok | world_patch | dialog |
| 740 | ok | goal_status |  |
| 741 | ok | decision_engine |  |
| 742 | ok | planner_decision |  |
| 743 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 744 | ok | step | app=WhatsApp screenshot=True |
| 745 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 746 | ok | step | fallback=pyobjc_ax |
| 747 | ok | step | nodes=1 elapsed=0.00s |
| 748 | ok | observation |  |
| 749 | ok | observation |  |
| 750 | ok | forward_task |  |
| 751 | ok | world_patch | dialog |
| 752 | ok | goal_status |  |
| 753 | ok | decision_engine |  |
| 754 | ok | planner_decision |  |
| 755 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 756 | ok | step | transition settle |
| 757 | ok | step | app=WhatsApp screenshot=True |
| 758 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 759 | ok | step | fallback=pyobjc_ax |
| 760 | ok | step | nodes=1 elapsed=0.00s |
| 761 | ok | observation |  |
| 762 | ok | step | transition poll |
| 763 | ok | step | app=WhatsApp screenshot=True |
| 764 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 765 | ok | step | fallback=pyobjc_ax |
| 766 | ok | step | nodes=1 elapsed=0.00s |
| 767 | ok | observation |  |
| 768 | ok | step | transition poll |
| 769 | ok | step | app=WhatsApp screenshot=True |
| 770 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 771 | ok | step | fallback=pyobjc_ax |
| 772 | ok | step | nodes=1 elapsed=0.00s |
| 773 | ok | observation |  |
| 774 | ok | step | transition poll |
| 775 | ok | step | app=WhatsApp screenshot=True |
| 776 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 777 | ok | step | fallback=pyobjc_ax |
| 778 | ok | step | nodes=1 elapsed=0.00s |
| 779 | ok | observation |  |
| 780 | ok | step | transition poll |
| 781 | ok | perception_retry |  |
| 782 | ok | step | perception retry (fusion_agreement_low) |
| 783 | ok | step | app=WhatsApp screenshot=True |
| 784 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 785 | ok | step | fallback=pyobjc_ax |
| 786 | ok | step | nodes=1 elapsed=0.00s |
| 787 | ok | observation |  |
| 788 | fail | perception_unsettled |  |
| 789 | ok | post_observation |  |
| 790 | ok | post_world_patch |  |
| 791 | fail | transition_eval |  |
| 792 | ok | transition_attribution |  |
| 793 | fail | verification |  |
| 794 | ok | step | app=WhatsApp screenshot=True |
| 795 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 796 | ok | step | fallback=pyobjc_ax |
| 797 | ok | step | nodes=1 elapsed=0.00s |
| 798 | ok | observation |  |
| 799 | ok | post_transition_richer_reobserve |  |
| 800 | fail | forward_predicate_rollback |  |
| 801 | ok | step | app=WhatsApp screenshot=True |
| 802 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 803 | ok | step | fallback=pyobjc_ax |
| 804 | ok | step | nodes=1 elapsed=0.00s |
| 805 | ok | observation |  |
| 806 | ok | observation |  |
| 807 | ok | forward_task |  |
| 808 | ok | world_patch | dialog |
| 809 | ok | goal_status |  |
| 810 | ok | decision_engine |  |
| 811 | ok | planner_decision |  |
| 812 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 813 | ok | step | app=WhatsApp screenshot=True |
| 814 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 815 | ok | step | fallback=pyobjc_ax |
| 816 | ok | step | nodes=1 elapsed=0.00s |
| 817 | ok | observation |  |
| 818 | ok | observation |  |
| 819 | ok | forward_task |  |
| 820 | ok | world_patch | dialog |
| 821 | ok | goal_status |  |
| 822 | ok | decision_engine |  |
| 823 | ok | planner_decision |  |
| 824 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 825 | ok | step | app=WhatsApp screenshot=True |
| 826 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 827 | ok | step | fallback=pyobjc_ax |
| 828 | ok | step | nodes=1 elapsed=0.01s |
| 829 | ok | observation |  |
| 830 | ok | observation |  |
| 831 | ok | forward_task |  |
| 832 | ok | world_patch | dialog |
| 833 | ok | goal_status |  |
| 834 | ok | decision_engine |  |
| 835 | ok | planner_decision |  |
| 836 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 837 | ok | step | transition settle |
| 838 | ok | step | app=WhatsApp screenshot=True |
| 839 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 840 | ok | step | fallback=pyobjc_ax |
| 841 | ok | step | nodes=1 elapsed=0.00s |
| 842 | ok | observation |  |
| 843 | ok | step | transition poll |
| 844 | ok | step | app=WhatsApp screenshot=True |
| 845 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 846 | ok | step | fallback=pyobjc_ax |
| 847 | ok | step | nodes=1 elapsed=0.00s |
| 848 | ok | observation |  |
| 849 | ok | step | transition poll |
| 850 | ok | step | app=WhatsApp screenshot=True |
| 851 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 852 | ok | step | fallback=pyobjc_ax |
| 853 | ok | step | nodes=1 elapsed=0.00s |
| 854 | ok | observation |  |
| 855 | ok | step | transition poll |
| 856 | ok | step | app=WhatsApp screenshot=True |
| 857 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 858 | ok | step | fallback=pyobjc_ax |
| 859 | ok | step | nodes=1 elapsed=0.00s |
| 860 | ok | observation |  |
| 861 | ok | step | transition poll |
| 862 | ok | perception_retry |  |
| 863 | ok | step | perception retry (fusion_agreement_low) |
| 864 | ok | step | app=WhatsApp screenshot=True |
| 865 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 866 | ok | step | fallback=pyobjc_ax |
| 867 | ok | step | nodes=1 elapsed=0.00s |
| 868 | ok | observation |  |
| 869 | fail | perception_unsettled |  |
| 870 | ok | post_observation |  |
| 871 | ok | post_world_patch |  |
| 872 | fail | transition_eval |  |
| 873 | ok | transition_attribution |  |
| 874 | fail | verification |  |
| 875 | ok | step | app=WhatsApp screenshot=True |
| 876 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 877 | ok | step | fallback=pyobjc_ax |
| 878 | ok | step | nodes=1 elapsed=0.00s |
| 879 | ok | observation |  |
| 880 | ok | post_transition_richer_reobserve |  |
| 881 | fail | forward_predicate_rollback |  |
| 882 | ok | step | app=WhatsApp screenshot=True |
| 883 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 884 | ok | step | fallback=pyobjc_ax |
| 885 | ok | step | nodes=1 elapsed=0.00s |
| 886 | ok | observation |  |
| 887 | ok | observation |  |
| 888 | ok | forward_task |  |
| 889 | ok | world_patch | dialog |
| 890 | ok | goal_status |  |
| 891 | ok | decision_engine |  |
| 892 | ok | planner_decision |  |
| 893 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 894 | ok | step | app=WhatsApp screenshot=True |
| 895 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 896 | ok | step | fallback=pyobjc_ax |
| 897 | ok | step | nodes=1 elapsed=0.00s |
| 898 | ok | observation |  |
| 899 | ok | observation |  |
| 900 | ok | forward_task |  |
| 901 | ok | world_patch | dialog |
| 902 | ok | goal_status |  |
| 903 | ok | decision_engine |  |
| 904 | ok | planner_decision |  |
| 905 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 906 | ok | step | app=WhatsApp screenshot=True |
| 907 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 908 | ok | step | fallback=pyobjc_ax |
| 909 | ok | step | nodes=1 elapsed=0.00s |
| 910 | ok | observation |  |
| 911 | ok | observation |  |
| 912 | ok | forward_task |  |
| 913 | ok | world_patch | dialog |
| 914 | ok | goal_status |  |
| 915 | ok | decision_engine |  |
| 916 | ok | planner_decision |  |
| 917 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 918 | ok | step | transition settle |
| 919 | ok | step | app=WhatsApp screenshot=True |
| 920 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 921 | ok | step | fallback=pyobjc_ax |
| 922 | ok | step | nodes=1 elapsed=0.00s |
| 923 | ok | observation |  |
| 924 | ok | step | transition poll |
| 925 | ok | step | app=WhatsApp screenshot=True |
| 926 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 927 | ok | step | fallback=pyobjc_ax |
| 928 | ok | step | nodes=1 elapsed=0.00s |
| 929 | ok | observation |  |
| 930 | ok | step | transition poll |
| 931 | ok | step | app=WhatsApp screenshot=True |
| 932 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 933 | ok | step | fallback=pyobjc_ax |
| 934 | ok | step | nodes=1 elapsed=0.00s |
| 935 | ok | observation |  |
| 936 | ok | step | transition poll |
| 937 | ok | perception_retry |  |
| 938 | ok | step | perception retry (fusion_agreement_low) |
| 939 | ok | step | app=WhatsApp screenshot=True |
| 940 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 941 | ok | step | fallback=pyobjc_ax |
| 942 | ok | step | nodes=1 elapsed=0.00s |
| 943 | ok | observation |  |
| 944 | fail | perception_unsettled |  |
| 945 | ok | post_observation |  |
| 946 | ok | post_world_patch |  |
| 947 | fail | transition_eval |  |
| 948 | ok | transition_attribution |  |
| 949 | fail | verification |  |
| 950 | ok | step | app=WhatsApp screenshot=True |
| 951 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 952 | ok | step | fallback=pyobjc_ax |
| 953 | ok | step | nodes=1 elapsed=0.00s |
| 954 | ok | observation |  |
| 955 | ok | post_transition_richer_reobserve |  |
| 956 | fail | forward_predicate_rollback |  |
| 957 | ok | step | app=WhatsApp screenshot=True |
| 958 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 959 | ok | step | fallback=pyobjc_ax |
| 960 | ok | step | nodes=1 elapsed=0.00s |
| 961 | ok | observation |  |
| 962 | ok | observation |  |
| 963 | ok | forward_task |  |
| 964 | ok | world_patch | dialog |
| 965 | ok | goal_status |  |
| 966 | ok | decision_engine |  |
| 967 | ok | planner_decision |  |
| 968 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 969 | ok | step | app=WhatsApp screenshot=True |
| 970 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 971 | ok | step | fallback=pyobjc_ax |
| 972 | ok | step | nodes=1 elapsed=0.00s |
| 973 | ok | observation |  |
| 974 | ok | observation |  |
| 975 | ok | forward_task |  |
| 976 | ok | world_patch | dialog |
| 977 | ok | goal_status |  |
| 978 | ok | decision_engine |  |
| 979 | ok | planner_decision |  |
| 980 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 981 | ok | step | app=WhatsApp screenshot=True |
| 982 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 983 | ok | step | fallback=pyobjc_ax |
| 984 | ok | step | nodes=1 elapsed=0.00s |
| 985 | ok | observation |  |
| 986 | ok | observation |  |
| 987 | ok | forward_task |  |
| 988 | ok | world_patch | dialog |
| 989 | ok | goal_status |  |
| 990 | ok | decision_engine |  |
| 991 | ok | planner_decision |  |
| 992 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 993 | ok | step | transition settle |
| 994 | ok | step | app=WhatsApp screenshot=True |
| 995 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 996 | ok | step | fallback=pyobjc_ax |
| 997 | ok | step | nodes=1 elapsed=0.00s |
| 998 | ok | observation |  |
| 999 | ok | step | transition poll |
| 1000 | ok | step | app=WhatsApp screenshot=True |
| 1001 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1002 | ok | step | fallback=pyobjc_ax |
| 1003 | ok | step | nodes=1 elapsed=0.00s |
| 1004 | ok | observation |  |
| 1005 | ok | step | transition poll |
| 1006 | ok | step | app=WhatsApp screenshot=True |
| 1007 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1008 | ok | step | fallback=pyobjc_ax |
| 1009 | ok | step | nodes=1 elapsed=0.00s |
| 1010 | ok | observation |  |
| 1011 | ok | step | transition poll |
| 1012 | ok | step | app=WhatsApp screenshot=True |
| 1013 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1014 | ok | step | fallback=pyobjc_ax |
| 1015 | ok | step | nodes=1 elapsed=0.00s |
| 1016 | ok | observation |  |
| 1017 | ok | step | transition poll |
| 1018 | ok | perception_retry |  |
| 1019 | ok | step | perception retry (fusion_agreement_low) |
| 1020 | ok | step | app=WhatsApp screenshot=True |
| 1021 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1022 | ok | step | fallback=pyobjc_ax |
| 1023 | ok | step | nodes=1 elapsed=0.00s |
| 1024 | ok | observation |  |
| 1025 | fail | perception_unsettled |  |
| 1026 | ok | post_observation |  |
| 1027 | ok | post_world_patch |  |
| 1028 | fail | transition_eval |  |
| 1029 | ok | transition_attribution |  |
| 1030 | fail | verification |  |
| 1031 | ok | step | app=WhatsApp screenshot=True |
| 1032 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1033 | ok | step | fallback=pyobjc_ax |
| 1034 | ok | step | nodes=1 elapsed=0.00s |
| 1035 | ok | observation |  |
| 1036 | ok | post_transition_richer_reobserve |  |
| 1037 | fail | forward_predicate_rollback |  |
| 1038 | ok | step | app=WhatsApp screenshot=True |
| 1039 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1040 | ok | step | fallback=pyobjc_ax |
| 1041 | ok | step | nodes=1 elapsed=0.00s |
| 1042 | ok | observation |  |
| 1043 | ok | observation |  |
| 1044 | ok | forward_task |  |
| 1045 | ok | world_patch | dialog |
| 1046 | ok | goal_status |  |
| 1047 | ok | decision_engine |  |
| 1048 | ok | planner_decision |  |
| 1049 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1050 | ok | step | app=WhatsApp screenshot=True |
| 1051 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1052 | ok | step | fallback=pyobjc_ax |
| 1053 | ok | step | nodes=1 elapsed=0.00s |
| 1054 | ok | observation |  |
| 1055 | ok | observation |  |
| 1056 | ok | forward_task |  |
| 1057 | ok | world_patch | dialog |
| 1058 | ok | goal_status |  |
| 1059 | ok | decision_engine |  |
| 1060 | ok | planner_decision |  |
| 1061 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1062 | ok | step | app=WhatsApp screenshot=True |
| 1063 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1064 | ok | step | fallback=pyobjc_ax |
| 1065 | ok | step | nodes=1 elapsed=0.00s |
| 1066 | ok | observation |  |
| 1067 | ok | observation |  |
| 1068 | ok | forward_task |  |
| 1069 | ok | world_patch | dialog |
| 1070 | ok | goal_status |  |
| 1071 | ok | decision_engine |  |
| 1072 | ok | planner_decision |  |
| 1073 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1074 | ok | step | transition settle |
| 1075 | ok | step | app=WhatsApp screenshot=True |
| 1076 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1077 | ok | step | fallback=pyobjc_ax |
| 1078 | ok | step | nodes=1 elapsed=0.00s |
| 1079 | ok | observation |  |
| 1080 | ok | step | transition poll |
| 1081 | ok | step | app=WhatsApp screenshot=True |
| 1082 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1083 | ok | step | fallback=pyobjc_ax |
| 1084 | ok | step | nodes=1 elapsed=0.00s |
| 1085 | ok | observation |  |
| 1086 | ok | step | transition poll |
| 1087 | ok | step | app=WhatsApp screenshot=True |
| 1088 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1089 | ok | step | fallback=pyobjc_ax |
| 1090 | ok | step | nodes=1 elapsed=0.00s |
| 1091 | ok | observation |  |
| 1092 | ok | step | transition poll |
| 1093 | ok | perception_retry |  |
| 1094 | ok | step | perception retry (fusion_agreement_low) |
| 1095 | ok | step | app=WhatsApp screenshot=True |
| 1096 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1097 | ok | step | fallback=pyobjc_ax |
| 1098 | ok | step | nodes=1 elapsed=0.00s |
| 1099 | ok | observation |  |
| 1100 | fail | perception_unsettled |  |
| 1101 | ok | post_observation |  |
| 1102 | ok | post_world_patch |  |
| 1103 | fail | transition_eval |  |
| 1104 | ok | transition_attribution |  |
| 1105 | fail | verification |  |
| 1106 | ok | step | app=WhatsApp screenshot=True |
| 1107 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1108 | ok | step | fallback=pyobjc_ax |
| 1109 | ok | step | nodes=1 elapsed=0.00s |
| 1110 | ok | observation |  |
| 1111 | ok | post_transition_richer_reobserve |  |
| 1112 | fail | forward_predicate_rollback |  |
| 1113 | ok | step | app=WhatsApp screenshot=True |
| 1114 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1115 | ok | step | fallback=pyobjc_ax |
| 1116 | ok | step | nodes=1 elapsed=0.00s |
| 1117 | ok | observation |  |
| 1118 | ok | observation |  |
| 1119 | ok | forward_task |  |
| 1120 | ok | world_patch | dialog |
| 1121 | ok | goal_status |  |
| 1122 | ok | decision_engine |  |
| 1123 | ok | planner_decision |  |
| 1124 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1125 | ok | step | app=WhatsApp screenshot=True |
| 1126 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1127 | ok | step | fallback=pyobjc_ax |
| 1128 | ok | step | nodes=1 elapsed=0.00s |
| 1129 | ok | observation |  |
| 1130 | ok | observation |  |
| 1131 | ok | forward_task |  |
| 1132 | ok | world_patch | dialog |
| 1133 | ok | goal_status |  |
| 1134 | ok | decision_engine |  |
| 1135 | ok | planner_decision |  |
| 1136 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1137 | ok | step | app=WhatsApp screenshot=True |
| 1138 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1139 | ok | step | fallback=pyobjc_ax |
| 1140 | ok | step | nodes=1 elapsed=0.00s |
| 1141 | ok | observation |  |
| 1142 | ok | observation |  |
| 1143 | ok | forward_task |  |
| 1144 | ok | world_patch | dialog |
| 1145 | ok | goal_status |  |
| 1146 | ok | decision_engine |  |
| 1147 | ok | planner_decision |  |
| 1148 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1149 | ok | step | transition settle |
| 1150 | ok | step | app=WhatsApp screenshot=True |
| 1151 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1152 | ok | step | fallback=pyobjc_ax |
| 1153 | ok | step | nodes=1 elapsed=0.00s |
| 1154 | ok | observation |  |
| 1155 | ok | step | transition poll |
| 1156 | ok | step | app=WhatsApp screenshot=True |
| 1157 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1158 | ok | step | fallback=pyobjc_ax |
| 1159 | ok | step | nodes=1 elapsed=0.00s |
| 1160 | ok | observation |  |
| 1161 | ok | step | transition poll |
| 1162 | ok | perception_retry |  |
| 1163 | ok | step | perception retry (fusion_agreement_low) |
| 1164 | ok | step | app=WhatsApp screenshot=True |
| 1165 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1166 | ok | step | fallback=pyobjc_ax |
| 1167 | ok | step | nodes=1 elapsed=0.00s |
| 1168 | ok | observation |  |
| 1169 | fail | perception_unsettled |  |
| 1170 | ok | post_observation |  |
| 1171 | ok | post_world_patch |  |
| 1172 | fail | transition_eval |  |
| 1173 | ok | transition_attribution |  |
| 1174 | fail | verification |  |
| 1175 | ok | step | app=WhatsApp screenshot=True |
| 1176 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1177 | ok | step | fallback=pyobjc_ax |
| 1178 | ok | step | nodes=1 elapsed=0.00s |
| 1179 | ok | observation |  |
| 1180 | ok | post_transition_richer_reobserve |  |
| 1181 | fail | forward_predicate_rollback |  |
| 1182 | ok | step | app=WhatsApp screenshot=True |
| 1183 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1184 | ok | step | fallback=pyobjc_ax |
| 1185 | ok | step | nodes=1 elapsed=0.00s |
| 1186 | ok | observation |  |
| 1187 | ok | observation |  |
| 1188 | ok | forward_task |  |
| 1189 | ok | world_patch | dialog |
| 1190 | ok | goal_status |  |
| 1191 | ok | decision_engine |  |
| 1192 | ok | planner_decision |  |
| 1193 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1194 | ok | step | app=WhatsApp screenshot=True |
| 1195 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1196 | ok | step | fallback=pyobjc_ax |
| 1197 | ok | step | nodes=1 elapsed=0.01s |
| 1198 | ok | observation |  |
| 1199 | ok | observation |  |
| 1200 | ok | forward_task |  |
| 1201 | ok | world_patch | dialog |
| 1202 | ok | goal_status |  |
| 1203 | ok | decision_engine |  |
| 1204 | ok | planner_decision |  |
| 1205 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1206 | ok | step | app=WhatsApp screenshot=True |
| 1207 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1208 | ok | step | fallback=pyobjc_ax |
| 1209 | ok | step | nodes=1 elapsed=0.00s |
| 1210 | ok | observation |  |
| 1211 | ok | observation |  |
| 1212 | ok | forward_task |  |
| 1213 | ok | world_patch | dialog |
| 1214 | ok | goal_status |  |
| 1215 | ok | decision_engine |  |
| 1216 | ok | planner_decision |  |
| 1217 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1218 | ok | step | transition settle |
| 1219 | ok | step | app=WhatsApp screenshot=True |
| 1220 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1221 | ok | step | fallback=pyobjc_ax |
| 1222 | ok | step | nodes=1 elapsed=0.00s |
| 1223 | ok | observation |  |
| 1224 | ok | step | transition poll |
| 1225 | ok | step | app=WhatsApp screenshot=True |
| 1226 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1227 | ok | step | fallback=pyobjc_ax |
| 1228 | ok | step | nodes=1 elapsed=0.00s |
| 1229 | ok | observation |  |
| 1230 | ok | step | transition poll |
| 1231 | ok | step | app=WhatsApp screenshot=True |
| 1232 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1233 | ok | step | fallback=pyobjc_ax |
| 1234 | ok | step | nodes=1 elapsed=0.00s |
| 1235 | ok | observation |  |
| 1236 | ok | step | transition poll |
| 1237 | ok | perception_retry |  |
| 1238 | ok | step | perception retry (fusion_agreement_low) |
| 1239 | ok | step | app=WhatsApp screenshot=True |
| 1240 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1241 | ok | step | fallback=pyobjc_ax |
| 1242 | ok | step | nodes=1 elapsed=0.01s |
| 1243 | ok | observation |  |
| 1244 | fail | perception_unsettled |  |
| 1245 | ok | post_observation |  |
| 1246 | ok | post_world_patch |  |
| 1247 | fail | transition_eval |  |
| 1248 | ok | transition_attribution |  |
| 1249 | fail | verification |  |
| 1250 | ok | step | app=WhatsApp screenshot=True |
| 1251 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1252 | ok | step | fallback=pyobjc_ax |
| 1253 | ok | step | nodes=1 elapsed=0.00s |
| 1254 | ok | observation |  |
| 1255 | ok | post_transition_richer_reobserve |  |
| 1256 | fail | forward_predicate_rollback |  |
| 1257 | ok | step | app=WhatsApp screenshot=True |
| 1258 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1259 | ok | step | fallback=pyobjc_ax |
| 1260 | ok | step | nodes=1 elapsed=0.00s |
| 1261 | ok | observation |  |
| 1262 | ok | observation |  |
| 1263 | ok | forward_task |  |
| 1264 | ok | world_patch | dialog |
| 1265 | ok | goal_status |  |
| 1266 | ok | decision_engine |  |
| 1267 | ok | planner_decision |  |
| 1268 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1269 | ok | step | app=WhatsApp screenshot=True |
| 1270 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1271 | ok | step | fallback=pyobjc_ax |
| 1272 | ok | step | nodes=1 elapsed=0.00s |
| 1273 | ok | observation |  |
| 1274 | ok | observation |  |
| 1275 | ok | forward_task |  |
| 1276 | ok | world_patch | dialog |
| 1277 | ok | goal_status |  |
| 1278 | ok | decision_engine |  |
| 1279 | ok | planner_decision |  |
| 1280 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1281 | ok | step | app=WhatsApp screenshot=True |
| 1282 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1283 | ok | step | fallback=pyobjc_ax |
| 1284 | ok | step | nodes=1 elapsed=0.00s |
| 1285 | ok | observation |  |
| 1286 | ok | observation |  |
| 1287 | ok | forward_task |  |
| 1288 | ok | world_patch | dialog |
| 1289 | ok | goal_status |  |
| 1290 | ok | decision_engine |  |
| 1291 | ok | planner_decision |  |
| 1292 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1293 | ok | step | transition settle |
| 1294 | ok | step | app=WhatsApp screenshot=True |
| 1295 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1296 | ok | step | fallback=pyobjc_ax |
| 1297 | ok | step | nodes=1 elapsed=0.01s |
| 1298 | ok | observation |  |
| 1299 | ok | step | transition poll |
| 1300 | ok | step | app=WhatsApp screenshot=True |
| 1301 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1302 | ok | step | fallback=pyobjc_ax |
| 1303 | ok | step | nodes=1 elapsed=0.00s |
| 1304 | ok | observation |  |
| 1305 | ok | step | transition poll |
| 1306 | ok | step | app=WhatsApp screenshot=True |
| 1307 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1308 | ok | step | fallback=pyobjc_ax |
| 1309 | ok | step | nodes=1 elapsed=0.00s |
| 1310 | ok | observation |  |
| 1311 | ok | step | transition poll |
| 1312 | ok | step | app=WhatsApp screenshot=True |
| 1313 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1314 | ok | step | fallback=pyobjc_ax |
| 1315 | ok | step | nodes=1 elapsed=0.00s |
| 1316 | ok | observation |  |
| 1317 | ok | step | transition poll |
| 1318 | ok | perception_retry |  |
| 1319 | ok | step | perception retry (fusion_agreement_low) |
| 1320 | ok | step | app=WhatsApp screenshot=True |
| 1321 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1322 | ok | step | fallback=pyobjc_ax |
| 1323 | ok | step | nodes=1 elapsed=0.00s |
| 1324 | ok | observation |  |
| 1325 | fail | perception_unsettled |  |
| 1326 | ok | post_observation |  |
| 1327 | ok | post_world_patch |  |
| 1328 | fail | transition_eval |  |
| 1329 | ok | transition_attribution |  |
| 1330 | fail | verification |  |
| 1331 | ok | step | app=WhatsApp screenshot=True |
| 1332 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1333 | ok | step | fallback=pyobjc_ax |
| 1334 | ok | step | nodes=1 elapsed=0.00s |
| 1335 | ok | observation |  |
| 1336 | ok | post_transition_richer_reobserve |  |
| 1337 | fail | forward_predicate_rollback |  |
| 1338 | ok | step | app=WhatsApp screenshot=True |
| 1339 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1340 | ok | step | fallback=pyobjc_ax |
| 1341 | ok | step | nodes=1 elapsed=0.00s |
| 1342 | ok | observation |  |
| 1343 | ok | observation |  |
| 1344 | ok | forward_task |  |
| 1345 | ok | world_patch | dialog |
| 1346 | ok | goal_status |  |
| 1347 | ok | decision_engine |  |
| 1348 | ok | planner_decision |  |
| 1349 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1350 | ok | step | app=WhatsApp screenshot=True |
| 1351 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1352 | ok | step | fallback=pyobjc_ax |
| 1353 | ok | step | nodes=1 elapsed=0.00s |
| 1354 | ok | observation |  |
| 1355 | ok | observation |  |
| 1356 | ok | forward_task |  |
| 1357 | ok | world_patch | dialog |
| 1358 | ok | goal_status |  |
| 1359 | ok | decision_engine |  |
| 1360 | ok | planner_decision |  |
| 1361 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1362 | ok | step | app=WhatsApp screenshot=True |
| 1363 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1364 | ok | step | fallback=pyobjc_ax |
| 1365 | ok | step | nodes=1 elapsed=0.00s |
| 1366 | ok | observation |  |
| 1367 | ok | observation |  |
| 1368 | ok | forward_task |  |
| 1369 | ok | world_patch | dialog |
| 1370 | ok | goal_status |  |
| 1371 | ok | decision_engine |  |
| 1372 | ok | planner_decision |  |
| 1373 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1374 | ok | step | transition settle |
| 1375 | ok | step | app=WhatsApp screenshot=True |
| 1376 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1377 | ok | step | fallback=pyobjc_ax |
| 1378 | ok | step | nodes=1 elapsed=0.01s |
| 1379 | ok | observation |  |
| 1380 | ok | step | transition poll |
| 1381 | ok | step | app=WhatsApp screenshot=True |
| 1382 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1383 | ok | step | fallback=pyobjc_ax |
| 1384 | ok | step | nodes=1 elapsed=0.00s |
| 1385 | ok | observation |  |
| 1386 | ok | step | transition poll |
| 1387 | ok | step | app=WhatsApp screenshot=True |
| 1388 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1389 | ok | step | fallback=pyobjc_ax |
| 1390 | ok | step | nodes=1 elapsed=0.00s |
| 1391 | ok | observation |  |
| 1392 | ok | step | transition poll |
| 1393 | ok | perception_retry |  |
| 1394 | ok | step | perception retry (fusion_agreement_low) |
| 1395 | ok | step | app=WhatsApp screenshot=True |
| 1396 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1397 | ok | step | fallback=pyobjc_ax |
| 1398 | ok | step | nodes=1 elapsed=0.00s |
| 1399 | ok | observation |  |
| 1400 | fail | perception_unsettled |  |
| 1401 | ok | post_observation |  |
| 1402 | ok | post_world_patch |  |
| 1403 | fail | transition_eval |  |
| 1404 | ok | transition_attribution |  |
| 1405 | fail | verification |  |
| 1406 | ok | step | app=WhatsApp screenshot=True |
| 1407 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1408 | ok | step | fallback=pyobjc_ax |
| 1409 | ok | step | nodes=1 elapsed=0.00s |
| 1410 | ok | observation |  |
| 1411 | ok | post_transition_richer_reobserve |  |
| 1412 | fail | forward_predicate_rollback |  |
| 1413 | ok | step | app=WhatsApp screenshot=True |
| 1414 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1415 | ok | step | fallback=pyobjc_ax |
| 1416 | ok | step | nodes=1 elapsed=0.00s |
| 1417 | ok | observation |  |
| 1418 | ok | observation |  |
| 1419 | ok | forward_task |  |
| 1420 | ok | world_patch | dialog |
| 1421 | ok | goal_status |  |
| 1422 | ok | decision_engine |  |
| 1423 | ok | planner_decision |  |
| 1424 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1425 | ok | step | app=WhatsApp screenshot=True |
| 1426 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1427 | ok | step | fallback=pyobjc_ax |
| 1428 | ok | step | nodes=1 elapsed=0.00s |
| 1429 | ok | observation |  |
| 1430 | ok | observation |  |
| 1431 | ok | forward_task |  |
| 1432 | ok | world_patch | dialog |
| 1433 | ok | goal_status |  |
| 1434 | ok | decision_engine |  |
| 1435 | ok | planner_decision |  |
| 1436 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1437 | ok | step | app=WhatsApp screenshot=True |
| 1438 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1439 | ok | step | fallback=pyobjc_ax |
| 1440 | ok | step | nodes=1 elapsed=0.00s |
| 1441 | ok | observation |  |
| 1442 | ok | observation |  |
| 1443 | ok | forward_task |  |
| 1444 | ok | world_patch | dialog |
| 1445 | ok | goal_status |  |
| 1446 | ok | decision_engine |  |
| 1447 | ok | planner_decision |  |
| 1448 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1449 | ok | step | transition settle |
| 1450 | ok | step | app=WhatsApp screenshot=True |
| 1451 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1452 | ok | step | fallback=pyobjc_ax |
| 1453 | ok | step | nodes=1 elapsed=0.00s |
| 1454 | ok | observation |  |
| 1455 | ok | step | transition poll |
| 1456 | ok | step | app=WhatsApp screenshot=True |
| 1457 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1458 | ok | step | fallback=pyobjc_ax |
| 1459 | ok | step | nodes=1 elapsed=0.00s |
| 1460 | ok | observation |  |
| 1461 | ok | step | transition poll |
| 1462 | ok | step | app=WhatsApp screenshot=True |
| 1463 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1464 | ok | step | fallback=pyobjc_ax |
| 1465 | ok | step | nodes=1 elapsed=0.00s |
| 1466 | ok | observation |  |
| 1467 | ok | step | transition poll |
| 1468 | ok | perception_retry |  |
| 1469 | ok | step | perception retry (fusion_agreement_low) |
| 1470 | ok | step | app=WhatsApp screenshot=True |
| 1471 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1472 | ok | step | fallback=pyobjc_ax |
| 1473 | ok | step | nodes=1 elapsed=0.00s |
| 1474 | ok | observation |  |
| 1475 | fail | perception_unsettled |  |
| 1476 | ok | post_observation |  |
| 1477 | ok | post_world_patch |  |
| 1478 | fail | transition_eval |  |
| 1479 | ok | transition_attribution |  |
| 1480 | fail | verification |  |
| 1481 | ok | step | app=WhatsApp screenshot=True |
| 1482 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1483 | ok | step | fallback=pyobjc_ax |
| 1484 | ok | step | nodes=1 elapsed=0.00s |
| 1485 | ok | observation |  |
| 1486 | ok | post_transition_richer_reobserve |  |
| 1487 | fail | forward_predicate_rollback |  |
| 1488 | ok | step | app=WhatsApp screenshot=True |
| 1489 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1490 | ok | step | fallback=pyobjc_ax |
| 1491 | ok | step | nodes=1 elapsed=0.00s |
| 1492 | ok | observation |  |
| 1493 | ok | observation |  |
| 1494 | ok | forward_task |  |
| 1495 | ok | world_patch | dialog |
| 1496 | ok | goal_status |  |
| 1497 | ok | decision_engine |  |
| 1498 | ok | planner_decision |  |
| 1499 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1500 | ok | step | app=WhatsApp screenshot=True |
| 1501 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1502 | ok | step | fallback=pyobjc_ax |
| 1503 | ok | step | nodes=1 elapsed=0.00s |
| 1504 | ok | observation |  |
| 1505 | ok | observation |  |
| 1506 | ok | forward_task |  |
| 1507 | ok | world_patch | dialog |
| 1508 | ok | goal_status |  |
| 1509 | ok | decision_engine |  |
| 1510 | ok | planner_decision |  |
| 1511 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1512 | ok | step | app=WhatsApp screenshot=True |
| 1513 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1514 | ok | step | fallback=pyobjc_ax |
| 1515 | ok | step | nodes=1 elapsed=0.00s |
| 1516 | ok | observation |  |
| 1517 | ok | observation |  |
| 1518 | ok | forward_task |  |
| 1519 | ok | world_patch | dialog |
| 1520 | ok | goal_status |  |
| 1521 | ok | decision_engine |  |
| 1522 | ok | planner_decision |  |
| 1523 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1524 | ok | step | transition settle |
| 1525 | ok | step | app=WhatsApp screenshot=True |
| 1526 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1527 | ok | step | fallback=pyobjc_ax |
| 1528 | ok | step | nodes=1 elapsed=0.00s |
| 1529 | ok | observation |  |
| 1530 | ok | step | transition poll |
| 1531 | ok | step | app=WhatsApp screenshot=True |
| 1532 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1533 | ok | step | fallback=pyobjc_ax |
| 1534 | ok | step | nodes=1 elapsed=0.01s |
| 1535 | ok | observation |  |
| 1536 | ok | step | transition poll |
| 1537 | ok | step | app=WhatsApp screenshot=True |
| 1538 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1539 | ok | step | fallback=pyobjc_ax |
| 1540 | ok | step | nodes=1 elapsed=0.00s |
| 1541 | ok | observation |  |
| 1542 | ok | step | transition poll |
| 1543 | ok | perception_retry |  |
| 1544 | ok | step | perception retry (fusion_agreement_low) |
| 1545 | ok | step | app=WhatsApp screenshot=True |
| 1546 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1547 | ok | step | fallback=pyobjc_ax |
| 1548 | ok | step | nodes=1 elapsed=0.00s |
| 1549 | ok | observation |  |
| 1550 | fail | perception_unsettled |  |
| 1551 | ok | post_observation |  |
| 1552 | ok | post_world_patch |  |
| 1553 | fail | transition_eval |  |
| 1554 | ok | transition_attribution |  |
| 1555 | fail | verification |  |
| 1556 | ok | step | app=WhatsApp screenshot=True |
| 1557 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1558 | ok | step | fallback=pyobjc_ax |
| 1559 | ok | step | nodes=1 elapsed=0.00s |
| 1560 | ok | observation |  |
| 1561 | ok | post_transition_richer_reobserve |  |
| 1562 | fail | forward_predicate_rollback |  |
| 1563 | ok | step | app=WhatsApp screenshot=True |
| 1564 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1565 | ok | step | fallback=pyobjc_ax |
| 1566 | ok | step | nodes=1 elapsed=0.00s |
| 1567 | ok | observation |  |
| 1568 | ok | observation |  |
| 1569 | ok | forward_task |  |
| 1570 | ok | world_patch | dialog |
| 1571 | ok | goal_status |  |
| 1572 | ok | decision_engine |  |
| 1573 | ok | planner_decision |  |
| 1574 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1575 | ok | step | app=WhatsApp screenshot=True |
| 1576 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1577 | ok | step | fallback=pyobjc_ax |
| 1578 | ok | step | nodes=1 elapsed=0.00s |
| 1579 | ok | observation |  |
| 1580 | ok | observation |  |
| 1581 | ok | forward_task |  |
| 1582 | ok | world_patch | dialog |
| 1583 | ok | goal_status |  |
| 1584 | ok | decision_engine |  |
| 1585 | ok | planner_decision |  |
| 1586 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1587 | ok | step | app=WhatsApp screenshot=True |
| 1588 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1589 | ok | step | fallback=pyobjc_ax |
| 1590 | ok | step | nodes=1 elapsed=0.00s |
| 1591 | ok | observation |  |
| 1592 | ok | observation |  |
| 1593 | ok | forward_task |  |
| 1594 | ok | world_patch | dialog |
| 1595 | ok | goal_status |  |
| 1596 | ok | decision_engine |  |
| 1597 | ok | planner_decision |  |
| 1598 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1599 | ok | step | transition settle |
| 1600 | ok | step | app=WhatsApp screenshot=True |
| 1601 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1602 | ok | step | fallback=pyobjc_ax |
| 1603 | ok | step | nodes=1 elapsed=0.00s |
| 1604 | ok | observation |  |
| 1605 | ok | step | transition poll |
| 1606 | ok | step | app=WhatsApp screenshot=True |
| 1607 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1608 | ok | step | fallback=pyobjc_ax |
| 1609 | ok | step | nodes=1 elapsed=0.00s |
| 1610 | ok | observation |  |
| 1611 | ok | step | transition poll |
| 1612 | ok | step | app=WhatsApp screenshot=True |
| 1613 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1614 | ok | step | fallback=pyobjc_ax |
| 1615 | ok | step | nodes=1 elapsed=0.00s |
| 1616 | ok | observation |  |
| 1617 | ok | step | transition poll |
| 1618 | ok | step | app=WhatsApp screenshot=True |
| 1619 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1620 | ok | step | fallback=pyobjc_ax |
| 1621 | ok | step | nodes=1 elapsed=0.00s |
| 1622 | ok | observation |  |
| 1623 | ok | step | transition poll |
| 1624 | ok | perception_retry |  |
| 1625 | ok | step | perception retry (fusion_agreement_low) |
| 1626 | ok | step | app=WhatsApp screenshot=True |
| 1627 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1628 | ok | step | fallback=pyobjc_ax |
| 1629 | ok | step | nodes=1 elapsed=0.00s |
| 1630 | ok | observation |  |
| 1631 | fail | perception_unsettled |  |
| 1632 | ok | post_observation |  |
| 1633 | ok | post_world_patch |  |
| 1634 | fail | transition_eval |  |
| 1635 | ok | transition_attribution |  |
| 1636 | fail | verification |  |
| 1637 | ok | step | app=WhatsApp screenshot=True |
| 1638 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1639 | ok | step | fallback=pyobjc_ax |
| 1640 | ok | step | nodes=1 elapsed=0.00s |
| 1641 | ok | observation |  |
| 1642 | ok | post_transition_richer_reobserve |  |
| 1643 | fail | forward_predicate_rollback |  |
| 1644 | ok | step | app=WhatsApp screenshot=True |
| 1645 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1646 | ok | step | fallback=pyobjc_ax |
| 1647 | ok | step | nodes=1 elapsed=0.00s |
| 1648 | ok | observation |  |
| 1649 | ok | observation |  |
| 1650 | ok | forward_task |  |
| 1651 | ok | world_patch | dialog |
| 1652 | ok | goal_status |  |
| 1653 | ok | decision_engine |  |
| 1654 | ok | planner_decision |  |
| 1655 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1656 | ok | step | app=WhatsApp screenshot=True |
| 1657 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1658 | ok | step | fallback=pyobjc_ax |
| 1659 | ok | step | nodes=1 elapsed=0.00s |
| 1660 | ok | observation |  |
| 1661 | ok | observation |  |
| 1662 | ok | forward_task |  |
| 1663 | ok | world_patch | dialog |
| 1664 | ok | goal_status |  |
| 1665 | ok | decision_engine |  |
| 1666 | ok | planner_decision |  |
| 1667 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1668 | ok | step | app=WhatsApp screenshot=True |
| 1669 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1670 | ok | step | fallback=pyobjc_ax |
| 1671 | ok | step | nodes=1 elapsed=0.00s |
| 1672 | ok | observation |  |
| 1673 | ok | observation |  |
| 1674 | ok | forward_task |  |
| 1675 | ok | world_patch | dialog |
| 1676 | ok | goal_status |  |
| 1677 | ok | decision_engine |  |
| 1678 | ok | planner_decision |  |
| 1679 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1680 | ok | step | transition settle |
| 1681 | ok | step | app=WhatsApp screenshot=True |
| 1682 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1683 | ok | step | fallback=pyobjc_ax |
| 1684 | ok | step | nodes=1 elapsed=0.00s |
| 1685 | ok | observation |  |
| 1686 | ok | step | transition poll |
| 1687 | ok | step | app=WhatsApp screenshot=True |
| 1688 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1689 | ok | step | fallback=pyobjc_ax |
| 1690 | ok | step | nodes=1 elapsed=0.00s |
| 1691 | ok | observation |  |
| 1692 | ok | step | transition poll |
| 1693 | ok | step | app=WhatsApp screenshot=True |
| 1694 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1695 | ok | step | fallback=pyobjc_ax |
| 1696 | ok | step | nodes=1 elapsed=0.00s |
| 1697 | ok | observation |  |
| 1698 | ok | step | transition poll |
| 1699 | ok | perception_retry |  |
| 1700 | ok | step | perception retry (fusion_agreement_low) |
| 1701 | ok | step | app=WhatsApp screenshot=True |
| 1702 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1703 | ok | step | fallback=pyobjc_ax |
| 1704 | ok | step | nodes=1 elapsed=0.00s |
| 1705 | ok | observation |  |
| 1706 | fail | perception_unsettled |  |
| 1707 | ok | post_observation |  |
| 1708 | ok | post_world_patch |  |
| 1709 | fail | transition_eval |  |
| 1710 | ok | transition_attribution |  |
| 1711 | fail | verification |  |
| 1712 | ok | step | app=WhatsApp screenshot=True |
| 1713 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1714 | ok | step | fallback=pyobjc_ax |
| 1715 | ok | step | nodes=1 elapsed=0.00s |
| 1716 | ok | observation |  |
| 1717 | ok | post_transition_richer_reobserve |  |
| 1718 | fail | forward_predicate_rollback |  |
| 1719 | ok | step | app=WhatsApp screenshot=True |
| 1720 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1721 | ok | step | fallback=pyobjc_ax |
| 1722 | ok | step | nodes=1 elapsed=0.00s |
| 1723 | ok | observation |  |
| 1724 | ok | observation |  |
| 1725 | ok | forward_task |  |
| 1726 | ok | world_patch | dialog |
| 1727 | ok | goal_status |  |
| 1728 | ok | decision_engine |  |
| 1729 | ok | planner_decision |  |
| 1730 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1731 | ok | step | app=WhatsApp screenshot=True |
| 1732 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1733 | ok | step | fallback=pyobjc_ax |
| 1734 | ok | step | nodes=1 elapsed=0.00s |
| 1735 | ok | observation |  |
| 1736 | ok | observation |  |
| 1737 | ok | forward_task |  |
| 1738 | ok | world_patch | dialog |
| 1739 | ok | goal_status |  |
| 1740 | ok | decision_engine |  |
| 1741 | ok | planner_decision |  |
| 1742 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1743 | ok | step | app=WhatsApp screenshot=True |
| 1744 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1745 | ok | step | fallback=pyobjc_ax |
| 1746 | ok | step | nodes=1 elapsed=0.00s |
| 1747 | ok | observation |  |
| 1748 | ok | observation |  |
| 1749 | ok | forward_task |  |
| 1750 | ok | world_patch | dialog |
| 1751 | ok | goal_status |  |
| 1752 | ok | decision_engine |  |
| 1753 | ok | planner_decision |  |
| 1754 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1755 | ok | step | transition settle |
| 1756 | ok | step | app=WhatsApp screenshot=True |
| 1757 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1758 | ok | step | fallback=pyobjc_ax |
| 1759 | ok | step | nodes=1 elapsed=0.00s |
| 1760 | ok | observation |  |
| 1761 | ok | step | transition poll |
| 1762 | ok | step | app=WhatsApp screenshot=True |
| 1763 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1764 | ok | step | fallback=pyobjc_ax |
| 1765 | ok | step | nodes=1 elapsed=0.00s |
| 1766 | ok | observation |  |
| 1767 | ok | step | transition poll |
| 1768 | ok | step | app=WhatsApp screenshot=True |
| 1769 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1770 | ok | step | fallback=pyobjc_ax |
| 1771 | ok | step | nodes=1 elapsed=0.00s |
| 1772 | ok | observation |  |
| 1773 | ok | step | transition poll |
| 1774 | ok | step | app=WhatsApp screenshot=True |
| 1775 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1776 | ok | step | fallback=pyobjc_ax |
| 1777 | ok | step | nodes=1 elapsed=0.00s |
| 1778 | ok | observation |  |
| 1779 | ok | step | transition poll |
| 1780 | ok | perception_retry |  |
| 1781 | ok | step | perception retry (fusion_agreement_low) |
| 1782 | ok | step | app=WhatsApp screenshot=True |
| 1783 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1784 | ok | step | fallback=pyobjc_ax |
| 1785 | ok | step | nodes=1 elapsed=0.00s |
| 1786 | ok | observation |  |
| 1787 | fail | perception_unsettled |  |
| 1788 | ok | post_observation |  |
| 1789 | ok | post_world_patch |  |
| 1790 | fail | transition_eval |  |
| 1791 | ok | transition_attribution |  |
| 1792 | fail | verification |  |
| 1793 | ok | step | app=WhatsApp screenshot=True |
| 1794 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1795 | ok | step | fallback=pyobjc_ax |
| 1796 | ok | step | nodes=1 elapsed=0.00s |
| 1797 | ok | observation |  |
| 1798 | ok | post_transition_richer_reobserve |  |
| 1799 | fail | forward_predicate_rollback |  |
| 1800 | ok | step | app=WhatsApp screenshot=True |
| 1801 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1802 | ok | step | fallback=pyobjc_ax |
| 1803 | ok | step | nodes=1 elapsed=0.00s |
| 1804 | ok | observation |  |
| 1805 | ok | observation |  |
| 1806 | ok | forward_task |  |
| 1807 | ok | world_patch | dialog |
| 1808 | ok | goal_status |  |
| 1809 | ok | decision_engine |  |
| 1810 | ok | planner_decision |  |
| 1811 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1812 | ok | step | app=WhatsApp screenshot=True |
| 1813 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1814 | ok | step | fallback=pyobjc_ax |
| 1815 | ok | step | nodes=1 elapsed=0.00s |
| 1816 | ok | observation |  |
| 1817 | ok | observation |  |
| 1818 | ok | forward_task |  |
| 1819 | ok | world_patch | dialog |
| 1820 | ok | goal_status |  |
| 1821 | ok | decision_engine |  |
| 1822 | ok | planner_decision |  |
| 1823 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1824 | ok | step | app=WhatsApp screenshot=True |
| 1825 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1826 | ok | step | fallback=pyobjc_ax |
| 1827 | ok | step | nodes=1 elapsed=0.00s |
| 1828 | ok | observation |  |
| 1829 | ok | observation |  |
| 1830 | ok | forward_task |  |
| 1831 | ok | world_patch | dialog |
| 1832 | ok | goal_status |  |
| 1833 | ok | decision_engine |  |
| 1834 | ok | planner_decision |  |
| 1835 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1836 | ok | step | transition settle |
| 1837 | ok | step | app=WhatsApp screenshot=True |
| 1838 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1839 | ok | step | fallback=pyobjc_ax |
| 1840 | ok | step | nodes=1 elapsed=0.00s |
| 1841 | ok | observation |  |
| 1842 | ok | step | transition poll |
| 1843 | ok | step | app=WhatsApp screenshot=True |
| 1844 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1845 | ok | step | fallback=pyobjc_ax |
| 1846 | ok | step | nodes=1 elapsed=0.00s |
| 1847 | ok | observation |  |
| 1848 | ok | step | transition poll |
| 1849 | ok | step | app=WhatsApp screenshot=True |
| 1850 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1851 | ok | step | fallback=pyobjc_ax |
| 1852 | ok | step | nodes=1 elapsed=0.00s |
| 1853 | ok | observation |  |
| 1854 | ok | step | transition poll |
| 1855 | ok | step | app=WhatsApp screenshot=True |
| 1856 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1857 | ok | step | fallback=pyobjc_ax |
| 1858 | ok | step | nodes=1 elapsed=0.00s |
| 1859 | ok | observation |  |
| 1860 | ok | step | transition poll |
| 1861 | ok | perception_retry |  |
| 1862 | ok | step | perception retry (fusion_agreement_low) |
| 1863 | ok | step | app=WhatsApp screenshot=True |
| 1864 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1865 | ok | step | fallback=pyobjc_ax |
| 1866 | ok | step | nodes=1 elapsed=0.00s |
| 1867 | ok | observation |  |
| 1868 | fail | perception_unsettled |  |
| 1869 | ok | post_observation |  |
| 1870 | ok | post_world_patch |  |
| 1871 | fail | transition_eval |  |
| 1872 | ok | transition_attribution |  |
| 1873 | fail | verification |  |
| 1874 | ok | step | app=WhatsApp screenshot=True |
| 1875 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1876 | ok | step | fallback=pyobjc_ax |
| 1877 | ok | step | nodes=1 elapsed=0.00s |
| 1878 | ok | observation |  |
| 1879 | ok | post_transition_richer_reobserve |  |
| 1880 | fail | forward_predicate_rollback |  |
| 1881 | ok | step | app=WhatsApp screenshot=True |
| 1882 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1883 | ok | step | fallback=pyobjc_ax |
| 1884 | ok | step | nodes=1 elapsed=0.00s |
| 1885 | ok | observation |  |
| 1886 | ok | observation |  |
| 1887 | ok | forward_task |  |
| 1888 | ok | world_patch | dialog |
| 1889 | ok | goal_status |  |
| 1890 | ok | decision_engine |  |
| 1891 | ok | planner_decision |  |
| 1892 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1893 | ok | step | app=WhatsApp screenshot=True |
| 1894 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1895 | ok | step | fallback=pyobjc_ax |
| 1896 | ok | step | nodes=1 elapsed=0.00s |
| 1897 | ok | observation |  |
| 1898 | ok | observation |  |
| 1899 | ok | forward_task |  |
| 1900 | ok | world_patch | dialog |
| 1901 | ok | goal_status |  |
| 1902 | ok | decision_engine |  |
| 1903 | ok | planner_decision |  |
| 1904 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1905 | ok | step | app=WhatsApp screenshot=True |
| 1906 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1907 | ok | step | fallback=pyobjc_ax |
| 1908 | ok | step | nodes=1 elapsed=0.00s |
| 1909 | ok | observation |  |
| 1910 | ok | observation |  |
| 1911 | ok | forward_task |  |
| 1912 | ok | world_patch | dialog |
| 1913 | ok | goal_status |  |
| 1914 | ok | decision_engine |  |
| 1915 | ok | planner_decision |  |
| 1916 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1917 | ok | step | transition settle |
| 1918 | ok | step | app=WhatsApp screenshot=True |
| 1919 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1920 | ok | step | fallback=pyobjc_ax |
| 1921 | ok | step | nodes=1 elapsed=0.00s |
| 1922 | ok | observation |  |
| 1923 | ok | step | transition poll |
| 1924 | ok | step | app=WhatsApp screenshot=True |
| 1925 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1926 | ok | step | fallback=pyobjc_ax |
| 1927 | ok | step | nodes=1 elapsed=0.00s |
| 1928 | ok | observation |  |
| 1929 | ok | step | transition poll |
| 1930 | ok | step | app=WhatsApp screenshot=True |
| 1931 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1932 | ok | step | fallback=pyobjc_ax |
| 1933 | ok | step | nodes=1 elapsed=0.00s |
| 1934 | ok | observation |  |
| 1935 | ok | step | transition poll |
| 1936 | ok | step | app=WhatsApp screenshot=True |
| 1937 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1938 | ok | step | fallback=pyobjc_ax |
| 1939 | ok | step | nodes=1 elapsed=0.00s |
| 1940 | ok | observation |  |
| 1941 | ok | step | transition poll |
| 1942 | ok | perception_retry |  |
| 1943 | ok | step | perception retry (fusion_agreement_low) |
| 1944 | ok | step | app=WhatsApp screenshot=True |
| 1945 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1946 | ok | step | fallback=pyobjc_ax |
| 1947 | ok | step | nodes=1 elapsed=0.00s |
| 1948 | ok | observation |  |
| 1949 | fail | perception_unsettled |  |
| 1950 | ok | post_observation |  |
| 1951 | ok | post_world_patch |  |
| 1952 | fail | transition_eval |  |
| 1953 | ok | transition_attribution |  |
| 1954 | fail | verification |  |
| 1955 | ok | step | app=WhatsApp screenshot=True |
| 1956 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1957 | ok | step | fallback=pyobjc_ax |
| 1958 | ok | step | nodes=1 elapsed=0.00s |
| 1959 | ok | observation |  |
| 1960 | ok | post_transition_richer_reobserve |  |
| 1961 | fail | forward_predicate_rollback |  |
| 1962 | ok | step | app=WhatsApp screenshot=True |
| 1963 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1964 | ok | step | fallback=pyobjc_ax |
| 1965 | ok | step | nodes=1 elapsed=0.00s |
| 1966 | ok | observation |  |
| 1967 | ok | observation |  |
| 1968 | ok | forward_task |  |
| 1969 | ok | world_patch | dialog |
| 1970 | ok | goal_status |  |
| 1971 | ok | decision_engine |  |
| 1972 | ok | planner_decision |  |
| 1973 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1974 | ok | step | app=WhatsApp screenshot=True |
| 1975 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1976 | ok | step | fallback=pyobjc_ax |
| 1977 | ok | step | nodes=1 elapsed=0.00s |
| 1978 | ok | observation |  |
| 1979 | ok | observation |  |
| 1980 | ok | forward_task |  |
| 1981 | ok | world_patch | dialog |
| 1982 | ok | goal_status |  |
| 1983 | ok | decision_engine |  |
| 1984 | ok | planner_decision |  |
| 1985 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1986 | ok | step | app=WhatsApp screenshot=True |
| 1987 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1988 | ok | step | fallback=pyobjc_ax |
| 1989 | ok | step | nodes=1 elapsed=0.00s |
| 1990 | ok | observation |  |
| 1991 | ok | observation |  |
| 1992 | ok | forward_task |  |
| 1993 | ok | world_patch | dialog |
| 1994 | ok | goal_status |  |
| 1995 | ok | decision_engine |  |
| 1996 | ok | planner_decision |  |
| 1997 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 1998 | ok | step | transition settle |
| 1999 | ok | step | app=WhatsApp screenshot=True |
| 2000 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2001 | ok | step | fallback=pyobjc_ax |
| 2002 | ok | step | nodes=1 elapsed=0.00s |
| 2003 | ok | observation |  |
| 2004 | ok | step | transition poll |
| 2005 | ok | step | app=WhatsApp screenshot=True |
| 2006 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2007 | ok | step | fallback=pyobjc_ax |
| 2008 | ok | step | nodes=1 elapsed=0.00s |
| 2009 | ok | observation |  |
| 2010 | ok | step | transition poll |
| 2011 | ok | perception_retry |  |
| 2012 | ok | step | perception retry (fusion_agreement_low) |
| 2013 | ok | step | app=WhatsApp screenshot=True |
| 2014 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2015 | ok | step | fallback=pyobjc_ax |
| 2016 | ok | step | nodes=1 elapsed=0.00s |
| 2017 | ok | observation |  |
| 2018 | fail | perception_unsettled |  |
| 2019 | ok | post_observation |  |
| 2020 | ok | post_world_patch |  |
| 2021 | fail | transition_eval |  |
| 2022 | ok | transition_attribution |  |
| 2023 | fail | verification |  |
| 2024 | ok | step | app=WhatsApp screenshot=True |
| 2025 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2026 | ok | step | fallback=pyobjc_ax |
| 2027 | ok | step | nodes=1 elapsed=0.00s |
| 2028 | ok | observation |  |
| 2029 | ok | post_transition_richer_reobserve |  |
| 2030 | fail | forward_predicate_rollback |  |
| 2031 | ok | step | app=WhatsApp screenshot=True |
| 2032 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2033 | ok | step | fallback=pyobjc_ax |
| 2034 | ok | step | nodes=1 elapsed=0.00s |
| 2035 | ok | observation |  |
| 2036 | ok | observation |  |
| 2037 | ok | forward_task |  |
| 2038 | ok | world_patch | dialog |
| 2039 | ok | goal_status |  |
| 2040 | ok | decision_engine |  |
| 2041 | ok | planner_decision |  |
| 2042 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2043 | ok | step | app=WhatsApp screenshot=True |
| 2044 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2045 | ok | step | fallback=pyobjc_ax |
| 2046 | ok | step | nodes=1 elapsed=0.00s |
| 2047 | ok | observation |  |
| 2048 | ok | observation |  |
| 2049 | ok | forward_task |  |
| 2050 | ok | world_patch | dialog |
| 2051 | ok | goal_status |  |
| 2052 | ok | decision_engine |  |
| 2053 | ok | planner_decision |  |
| 2054 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2055 | ok | step | app=WhatsApp screenshot=True |
| 2056 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2057 | ok | step | fallback=pyobjc_ax |
| 2058 | ok | step | nodes=1 elapsed=0.00s |
| 2059 | ok | observation |  |
| 2060 | ok | observation |  |
| 2061 | ok | forward_task |  |
| 2062 | ok | world_patch | dialog |
| 2063 | ok | goal_status |  |
| 2064 | ok | decision_engine |  |
| 2065 | ok | planner_decision |  |
| 2066 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2067 | ok | step | transition settle |
| 2068 | ok | step | app=WhatsApp screenshot=True |
| 2069 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2070 | ok | step | fallback=pyobjc_ax |
| 2071 | ok | step | nodes=1 elapsed=0.00s |
| 2072 | ok | observation |  |
| 2073 | ok | step | transition poll |
| 2074 | ok | step | app=WhatsApp screenshot=True |
| 2075 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2076 | ok | step | fallback=pyobjc_ax |
| 2077 | ok | step | nodes=1 elapsed=0.00s |
| 2078 | ok | observation |  |
| 2079 | ok | step | transition poll |
| 2080 | ok | perception_retry |  |
| 2081 | ok | step | perception retry (fusion_agreement_low) |
| 2082 | ok | step | app=WhatsApp screenshot=True |
| 2083 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2084 | ok | step | fallback=pyobjc_ax |
| 2085 | ok | step | nodes=1 elapsed=0.00s |
| 2086 | ok | observation |  |
| 2087 | fail | perception_unsettled |  |
| 2088 | ok | post_observation |  |
| 2089 | ok | post_world_patch |  |
| 2090 | fail | transition_eval |  |
| 2091 | ok | transition_attribution |  |
| 2092 | fail | verification |  |
| 2093 | ok | step | app=WhatsApp screenshot=True |
| 2094 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2095 | ok | step | fallback=pyobjc_ax |
| 2096 | ok | step | nodes=1 elapsed=0.00s |
| 2097 | ok | observation |  |
| 2098 | ok | post_transition_richer_reobserve |  |
| 2099 | fail | forward_predicate_rollback |  |
| 2100 | ok | step | app=WhatsApp screenshot=True |
| 2101 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2102 | ok | step | fallback=pyobjc_ax |
| 2103 | ok | step | nodes=1 elapsed=0.00s |
| 2104 | ok | observation |  |
| 2105 | ok | observation |  |
| 2106 | ok | forward_task |  |
| 2107 | ok | world_patch | dialog |
| 2108 | ok | goal_status |  |
| 2109 | ok | decision_engine |  |
| 2110 | ok | planner_decision |  |
| 2111 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2112 | ok | step | app=WhatsApp screenshot=True |
| 2113 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2114 | ok | step | fallback=pyobjc_ax |
| 2115 | ok | step | nodes=1 elapsed=0.00s |
| 2116 | ok | observation |  |
| 2117 | ok | observation |  |
| 2118 | ok | forward_task |  |
| 2119 | ok | world_patch | dialog |
| 2120 | ok | goal_status |  |
| 2121 | ok | decision_engine |  |
| 2122 | ok | planner_decision |  |
| 2123 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2124 | ok | step | app=WhatsApp screenshot=True |
| 2125 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2126 | ok | step | fallback=pyobjc_ax |
| 2127 | ok | step | nodes=1 elapsed=0.00s |
| 2128 | ok | observation |  |
| 2129 | ok | observation |  |
| 2130 | ok | forward_task |  |
| 2131 | ok | world_patch | dialog |
| 2132 | ok | goal_status |  |
| 2133 | ok | decision_engine |  |
| 2134 | ok | planner_decision |  |
| 2135 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2136 | ok | step | transition settle |
| 2137 | ok | step | app=WhatsApp screenshot=True |
| 2138 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2139 | ok | step | fallback=pyobjc_ax |
| 2140 | ok | step | nodes=1 elapsed=0.01s |
| 2141 | ok | observation |  |
| 2142 | ok | step | transition poll |
| 2143 | ok | step | app=WhatsApp screenshot=True |
| 2144 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2145 | ok | step | fallback=pyobjc_ax |
| 2146 | ok | step | nodes=1 elapsed=0.00s |
| 2147 | ok | observation |  |
| 2148 | ok | step | transition poll |
| 2149 | ok | step | app=WhatsApp screenshot=True |
| 2150 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2151 | ok | step | fallback=pyobjc_ax |
| 2152 | ok | step | nodes=1 elapsed=0.00s |
| 2153 | ok | observation |  |
| 2154 | ok | step | transition poll |
| 2155 | ok | perception_retry |  |
| 2156 | ok | step | perception retry (fusion_agreement_low) |
| 2157 | ok | step | app=WhatsApp screenshot=True |
| 2158 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2159 | ok | step | fallback=pyobjc_ax |
| 2160 | ok | step | nodes=1 elapsed=0.00s |
| 2161 | ok | observation |  |
| 2162 | fail | perception_unsettled |  |
| 2163 | ok | post_observation |  |
| 2164 | ok | post_world_patch |  |
| 2165 | fail | transition_eval |  |
| 2166 | ok | transition_attribution |  |
| 2167 | fail | verification |  |
| 2168 | ok | step | app=WhatsApp screenshot=True |
| 2169 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2170 | ok | step | fallback=pyobjc_ax |
| 2171 | ok | step | nodes=1 elapsed=0.00s |
| 2172 | ok | observation |  |
| 2173 | ok | post_transition_richer_reobserve |  |
| 2174 | fail | forward_predicate_rollback |  |
| 2175 | ok | step | app=WhatsApp screenshot=True |
| 2176 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2177 | ok | step | fallback=pyobjc_ax |
| 2178 | ok | step | nodes=1 elapsed=0.00s |
| 2179 | ok | observation |  |
| 2180 | ok | observation |  |
| 2181 | ok | forward_task |  |
| 2182 | ok | world_patch | dialog |
| 2183 | ok | goal_status |  |
| 2184 | ok | decision_engine |  |
| 2185 | ok | planner_decision |  |
| 2186 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2187 | ok | step | app=WhatsApp screenshot=True |
| 2188 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2189 | ok | step | fallback=pyobjc_ax |
| 2190 | ok | step | nodes=1 elapsed=0.00s |
| 2191 | ok | observation |  |
| 2192 | ok | observation |  |
| 2193 | ok | forward_task |  |
| 2194 | ok | world_patch | dialog |
| 2195 | ok | goal_status |  |
| 2196 | ok | decision_engine |  |
| 2197 | ok | planner_decision |  |
| 2198 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2199 | ok | step | app=WhatsApp screenshot=True |
| 2200 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2201 | ok | step | fallback=pyobjc_ax |
| 2202 | ok | step | nodes=1 elapsed=0.00s |
| 2203 | ok | observation |  |
| 2204 | ok | observation |  |
| 2205 | ok | forward_task |  |
| 2206 | ok | world_patch | dialog |
| 2207 | ok | goal_status |  |
| 2208 | ok | decision_engine |  |
| 2209 | ok | planner_decision |  |
| 2210 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2211 | ok | step | transition settle |
| 2212 | ok | step | app=WhatsApp screenshot=True |
| 2213 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2214 | ok | step | fallback=pyobjc_ax |
| 2215 | ok | step | nodes=1 elapsed=0.00s |
| 2216 | ok | observation |  |
| 2217 | ok | step | transition poll |
| 2218 | ok | step | app=WhatsApp screenshot=True |
| 2219 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2220 | ok | step | fallback=pyobjc_ax |
| 2221 | ok | step | nodes=1 elapsed=0.00s |
| 2222 | ok | observation |  |
| 2223 | ok | step | transition poll |
| 2224 | ok | step | app=WhatsApp screenshot=True |
| 2225 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2226 | ok | step | fallback=pyobjc_ax |
| 2227 | ok | step | nodes=1 elapsed=0.00s |
| 2228 | ok | observation |  |
| 2229 | ok | step | transition poll |
| 2230 | ok | step | app=WhatsApp screenshot=True |
| 2231 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2232 | ok | step | fallback=pyobjc_ax |
| 2233 | ok | step | nodes=1 elapsed=0.00s |
| 2234 | ok | observation |  |
| 2235 | ok | step | transition poll |
| 2236 | ok | perception_retry |  |
| 2237 | ok | step | perception retry (fusion_agreement_low) |
| 2238 | ok | step | app=WhatsApp screenshot=True |
| 2239 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2240 | ok | step | fallback=pyobjc_ax |
| 2241 | ok | step | nodes=1 elapsed=0.00s |
| 2242 | ok | observation |  |
| 2243 | fail | perception_unsettled |  |
| 2244 | ok | post_observation |  |
| 2245 | ok | post_world_patch |  |
| 2246 | fail | transition_eval |  |
| 2247 | ok | transition_attribution |  |
| 2248 | fail | verification |  |
| 2249 | ok | step | app=WhatsApp screenshot=True |
| 2250 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2251 | ok | step | fallback=pyobjc_ax |
| 2252 | ok | step | nodes=1 elapsed=0.00s |
| 2253 | ok | observation |  |
| 2254 | ok | post_transition_richer_reobserve |  |
| 2255 | fail | forward_predicate_rollback |  |
| 2256 | ok | step | app=WhatsApp screenshot=True |
| 2257 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2258 | ok | step | fallback=pyobjc_ax |
| 2259 | ok | step | nodes=1 elapsed=0.00s |
| 2260 | ok | observation |  |
| 2261 | ok | observation |  |
| 2262 | ok | forward_task |  |
| 2263 | ok | world_patch | dialog |
| 2264 | ok | goal_status |  |
| 2265 | ok | decision_engine |  |
| 2266 | ok | planner_decision |  |
| 2267 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2268 | ok | step | app=WhatsApp screenshot=True |
| 2269 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2270 | ok | step | fallback=pyobjc_ax |
| 2271 | ok | step | nodes=1 elapsed=0.00s |
| 2272 | ok | observation |  |
| 2273 | ok | observation |  |
| 2274 | ok | forward_task |  |
| 2275 | ok | world_patch | dialog |
| 2276 | ok | goal_status |  |
| 2277 | ok | decision_engine |  |
| 2278 | ok | planner_decision |  |
| 2279 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2280 | ok | step | app=WhatsApp screenshot=True |
| 2281 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2282 | ok | step | fallback=pyobjc_ax |
| 2283 | ok | step | nodes=1 elapsed=0.00s |
| 2284 | ok | observation |  |
| 2285 | ok | observation |  |
| 2286 | ok | forward_task |  |
| 2287 | ok | world_patch | dialog |
| 2288 | ok | goal_status |  |
| 2289 | ok | decision_engine |  |
| 2290 | ok | planner_decision |  |
| 2291 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2292 | ok | step | transition settle |
| 2293 | ok | step | app=WhatsApp screenshot=True |
| 2294 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2295 | ok | step | fallback=pyobjc_ax |
| 2296 | ok | step | nodes=1 elapsed=0.00s |
| 2297 | ok | observation |  |
| 2298 | ok | step | transition poll |
| 2299 | ok | step | app=WhatsApp screenshot=True |
| 2300 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2301 | ok | step | fallback=pyobjc_ax |
| 2302 | ok | step | nodes=1 elapsed=0.00s |
| 2303 | ok | observation |  |
| 2304 | ok | step | transition poll |
| 2305 | ok | step | app=WhatsApp screenshot=True |
| 2306 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2307 | ok | step | fallback=pyobjc_ax |
| 2308 | ok | step | nodes=1 elapsed=0.00s |
| 2309 | ok | observation |  |
| 2310 | ok | step | transition poll |
| 2311 | ok | perception_retry |  |
| 2312 | ok | step | perception retry (fusion_agreement_low) |
| 2313 | ok | step | app=WhatsApp screenshot=True |
| 2314 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2315 | ok | step | fallback=pyobjc_ax |
| 2316 | ok | step | nodes=1 elapsed=0.00s |
| 2317 | ok | observation |  |
| 2318 | fail | perception_unsettled |  |
| 2319 | ok | post_observation |  |
| 2320 | ok | post_world_patch |  |
| 2321 | fail | transition_eval |  |
| 2322 | ok | transition_attribution |  |
| 2323 | fail | verification |  |
| 2324 | ok | step | app=WhatsApp screenshot=True |
| 2325 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2326 | ok | step | fallback=pyobjc_ax |
| 2327 | ok | step | nodes=1 elapsed=0.00s |
| 2328 | ok | observation |  |
| 2329 | ok | post_transition_richer_reobserve |  |
| 2330 | fail | forward_predicate_rollback |  |
| 2331 | ok | step | app=WhatsApp screenshot=True |
| 2332 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2333 | ok | step | fallback=pyobjc_ax |
| 2334 | ok | step | nodes=1 elapsed=0.00s |
| 2335 | ok | observation |  |
| 2336 | ok | observation |  |
| 2337 | ok | forward_task |  |
| 2338 | ok | world_patch | dialog |
| 2339 | ok | goal_status |  |
| 2340 | ok | decision_engine |  |
| 2341 | ok | planner_decision |  |
| 2342 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2343 | ok | step | app=WhatsApp screenshot=True |
| 2344 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2345 | ok | step | fallback=pyobjc_ax |
| 2346 | ok | step | nodes=1 elapsed=0.00s |
| 2347 | ok | observation |  |
| 2348 | ok | observation |  |
| 2349 | ok | forward_task |  |
| 2350 | ok | world_patch | dialog |
| 2351 | ok | goal_status |  |
| 2352 | ok | decision_engine |  |
| 2353 | ok | planner_decision |  |
| 2354 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2355 | ok | step | app=WhatsApp screenshot=True |
| 2356 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2357 | ok | step | fallback=pyobjc_ax |
| 2358 | ok | step | nodes=1 elapsed=0.00s |
| 2359 | ok | observation |  |
| 2360 | ok | observation |  |
| 2361 | ok | forward_task |  |
| 2362 | ok | world_patch | dialog |
| 2363 | ok | goal_status |  |
| 2364 | ok | decision_engine |  |
| 2365 | ok | planner_decision |  |
| 2366 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2367 | ok | step | transition settle |
| 2368 | ok | step | app=WhatsApp screenshot=True |
| 2369 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2370 | ok | step | fallback=pyobjc_ax |
| 2371 | ok | step | nodes=1 elapsed=0.00s |
| 2372 | ok | observation |  |
| 2373 | ok | step | transition poll |
| 2374 | ok | step | app=WhatsApp screenshot=True |
| 2375 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2376 | ok | step | fallback=pyobjc_ax |
| 2377 | ok | step | nodes=1 elapsed=0.00s |
| 2378 | ok | observation |  |
| 2379 | ok | step | transition poll |
| 2380 | ok | step | app=WhatsApp screenshot=True |
| 2381 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2382 | ok | step | fallback=pyobjc_ax |
| 2383 | ok | step | nodes=1 elapsed=0.00s |
| 2384 | ok | observation |  |
| 2385 | ok | step | transition poll |
| 2386 | ok | perception_retry |  |
| 2387 | ok | step | perception retry (fusion_agreement_low) |
| 2388 | ok | step | app=WhatsApp screenshot=True |
| 2389 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2390 | ok | step | fallback=pyobjc_ax |
| 2391 | ok | step | nodes=1 elapsed=0.00s |
| 2392 | ok | observation |  |
| 2393 | fail | perception_unsettled |  |
| 2394 | ok | post_observation |  |
| 2395 | ok | post_world_patch |  |
| 2396 | fail | transition_eval |  |
| 2397 | ok | transition_attribution |  |
| 2398 | fail | verification |  |
| 2399 | ok | step | app=WhatsApp screenshot=True |
| 2400 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2401 | ok | step | fallback=pyobjc_ax |
| 2402 | ok | step | nodes=1 elapsed=0.00s |
| 2403 | ok | observation |  |
| 2404 | ok | post_transition_richer_reobserve |  |
| 2405 | fail | forward_predicate_rollback |  |
| 2406 | ok | step | app=WhatsApp screenshot=True |
| 2407 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2408 | ok | step | fallback=pyobjc_ax |
| 2409 | ok | step | nodes=1 elapsed=0.00s |
| 2410 | ok | observation |  |
| 2411 | ok | observation |  |
| 2412 | ok | forward_task |  |
| 2413 | ok | world_patch | dialog |
| 2414 | ok | goal_status |  |
| 2415 | ok | decision_engine |  |
| 2416 | ok | planner_decision |  |
| 2417 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2418 | ok | step | app=WhatsApp screenshot=True |
| 2419 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2420 | ok | step | fallback=pyobjc_ax |
| 2421 | ok | step | nodes=1 elapsed=0.00s |
| 2422 | ok | observation |  |
| 2423 | ok | observation |  |
| 2424 | ok | forward_task |  |
| 2425 | ok | world_patch | dialog |
| 2426 | ok | goal_status |  |
| 2427 | ok | decision_engine |  |
| 2428 | ok | planner_decision |  |
| 2429 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2430 | ok | step | app=WhatsApp screenshot=True |
| 2431 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2432 | ok | step | fallback=pyobjc_ax |
| 2433 | ok | step | nodes=1 elapsed=0.00s |
| 2434 | ok | observation |  |
| 2435 | ok | observation |  |
| 2436 | ok | forward_task |  |
| 2437 | ok | world_patch | dialog |
| 2438 | ok | goal_status |  |
| 2439 | ok | decision_engine |  |
| 2440 | ok | planner_decision |  |
| 2441 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2442 | ok | step | transition settle |
| 2443 | ok | step | app=WhatsApp screenshot=True |
| 2444 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2445 | ok | step | fallback=pyobjc_ax |
| 2446 | ok | step | nodes=1 elapsed=0.00s |
| 2447 | ok | observation |  |
| 2448 | ok | step | transition poll |
| 2449 | ok | step | app=WhatsApp screenshot=True |
| 2450 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2451 | ok | step | fallback=pyobjc_ax |
| 2452 | ok | step | nodes=1 elapsed=0.00s |
| 2453 | ok | observation |  |
| 2454 | ok | step | transition poll |
| 2455 | ok | step | app=WhatsApp screenshot=True |
| 2456 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2457 | ok | step | fallback=pyobjc_ax |
| 2458 | ok | step | nodes=1 elapsed=0.01s |
| 2459 | ok | observation |  |
| 2460 | ok | step | transition poll |
| 2461 | ok | perception_retry |  |
| 2462 | ok | step | perception retry (fusion_agreement_low) |
| 2463 | ok | step | app=WhatsApp screenshot=True |
| 2464 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2465 | ok | step | fallback=pyobjc_ax |
| 2466 | ok | step | nodes=1 elapsed=0.00s |
| 2467 | ok | observation |  |
| 2468 | fail | perception_unsettled |  |
| 2469 | ok | post_observation |  |
| 2470 | ok | post_world_patch |  |
| 2471 | fail | transition_eval |  |
| 2472 | ok | transition_attribution |  |
| 2473 | fail | verification |  |
| 2474 | ok | step | app=WhatsApp screenshot=True |
| 2475 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2476 | ok | step | fallback=pyobjc_ax |
| 2477 | ok | step | nodes=1 elapsed=0.00s |
| 2478 | ok | observation |  |
| 2479 | ok | post_transition_richer_reobserve |  |
| 2480 | fail | forward_predicate_rollback |  |
| 2481 | ok | step | app=WhatsApp screenshot=True |
| 2482 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2483 | ok | step | fallback=pyobjc_ax |
| 2484 | ok | step | nodes=1 elapsed=0.00s |
| 2485 | ok | observation |  |
| 2486 | ok | observation |  |
| 2487 | ok | forward_task |  |
| 2488 | ok | world_patch | dialog |
| 2489 | ok | goal_status |  |
| 2490 | ok | decision_engine |  |
| 2491 | ok | planner_decision |  |
| 2492 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2493 | ok | step | app=WhatsApp screenshot=True |
| 2494 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2495 | ok | step | fallback=pyobjc_ax |
| 2496 | ok | step | nodes=1 elapsed=0.00s |
| 2497 | ok | observation |  |
| 2498 | ok | observation |  |
| 2499 | ok | forward_task |  |
| 2500 | ok | world_patch | dialog |
| 2501 | ok | goal_status |  |
| 2502 | ok | decision_engine |  |
| 2503 | ok | planner_decision |  |
| 2504 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2505 | ok | step | app=WhatsApp screenshot=True |
| 2506 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2507 | ok | step | fallback=pyobjc_ax |
| 2508 | ok | step | nodes=1 elapsed=0.00s |
| 2509 | ok | observation |  |
| 2510 | ok | observation |  |
| 2511 | ok | forward_task |  |
| 2512 | ok | world_patch | dialog |
| 2513 | ok | goal_status |  |
| 2514 | ok | decision_engine |  |
| 2515 | ok | planner_decision |  |
| 2516 | ok | execution | click 'Exit WhatsApp' center=(600.0, 809.0) via entity bounds |
| 2517 | ok | step | transition settle |
| 2518 | ok | step | app=WhatsApp screenshot=True |
| 2519 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2520 | ok | step | fallback=pyobjc_ax |
| 2521 | ok | step | nodes=1 elapsed=0.00s |
| 2522 | ok | observation |  |
| 2523 | ok | step | transition poll |
| 2524 | ok | step | app=WhatsApp screenshot=True |
| 2525 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2526 | ok | step | fallback=pyobjc_ax |
| 2527 | ok | step | nodes=1 elapsed=0.00s |
| 2528 | ok | observation |  |
| 2529 | ok | step | transition poll |
| 2530 | ok | step | app=WhatsApp screenshot=True |
| 2531 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2532 | ok | step | fallback=pyobjc_ax |
| 2533 | ok | step | nodes=1 elapsed=0.01s |
| 2534 | ok | observation |  |
| 2535 | ok | step | transition poll |
| 2536 | ok | perception_retry |  |
| 2537 | ok | step | perception retry (fusion_agreement_low) |
| 2538 | ok | step | app=WhatsApp screenshot=True |
| 2539 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2540 | ok | step | fallback=pyobjc_ax |
| 2541 | ok | step | nodes=1 elapsed=0.05s |
| 2542 | ok | observation |  |
| 2543 | fail | perception_unsettled |  |
| 2544 | ok | post_observation |  |
| 2545 | ok | post_world_patch |  |
| 2546 | fail | transition_eval |  |
| 2547 | ok | transition_attribution |  |
| 2548 | fail | verification |  |
| 2549 | ok | step | app=WhatsApp screenshot=True |
| 2550 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2551 | ok | step | fallback=pyobjc_ax |
| 2552 | ok | step | nodes=1 elapsed=0.00s |
| 2553 | ok | observation |  |
| 2554 | ok | post_transition_richer_reobserve |  |
| 2555 | fail | forward_predicate_rollback |  |
| 2556 | ok | step | app=WhatsApp screenshot=True |
| 2557 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2558 | ok | step | fallback=pyobjc_ax |
| 2559 | ok | step | nodes=1 elapsed=0.00s |
| 2560 | ok | observation |  |
| 2561 | ok | observation |  |
| 2562 | ok | forward_task |  |
| 2563 | ok | world_patch | dialog |
| 2564 | ok | goal_status |  |
| 2565 | ok | decision_engine |  |
| 2566 | ok | planner_decision |  |
| 2567 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2568 | ok | step | app=WhatsApp screenshot=True |
| 2569 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2570 | ok | step | fallback=pyobjc_ax |
| 2571 | ok | step | nodes=1 elapsed=0.00s |
| 2572 | ok | observation |  |
| 2573 | ok | observation |  |
| 2574 | ok | forward_task |  |
| 2575 | ok | world_patch | dialog |
| 2576 | ok | goal_status |  |
| 2577 | ok | decision_engine |  |
| 2578 | ok | planner_decision |  |
| 2579 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2580 | ok | world_summary |  |
| 2581 | fail | check | fail |
| 2582 | fail | run_end | closed_loop ok=False reason='Maximum step count reached' iterations=99 |

## Failures

- seq=5 `check`: {"ts": 1785219845.494517, "seq": 5, "run_id": "wa-forward-live-1785219845", "kind": "check", "status": "fail", "name": "ghost_cli_installed", "expected": true, "actual": false, "message": "fail", "ste
- seq=83 `perception_unsettled`: {"ts": 1785219897.600537, "seq": 83, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_strat
- seq=86 `transition_eval`: {"ts": 1785219897.622633, "seq": 86, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family": 
- seq=88 `verification`: {"ts": 1785219897.623138, "seq": 88, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=95 `forward_predicate_rollback`: {"ts": 1785219897.801939, "seq": 95, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward_
- seq=164 `perception_unsettled`: {"ts": 1785219916.3057559, "seq": 164, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=167 `transition_eval`: {"ts": 1785219916.329319, "seq": 167, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=169 `verification`: {"ts": 1785219916.3299022, "seq": 169, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=176 `forward_predicate_rollback`: {"ts": 1785219916.7067788, "seq": 176, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=245 `perception_unsettled`: {"ts": 1785219934.905497, "seq": 245, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=248 `transition_eval`: {"ts": 1785219934.921899, "seq": 248, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=250 `verification`: {"ts": 1785219934.922227, "seq": 250, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=257 `forward_predicate_rollback`: {"ts": 1785219935.0537112, "seq": 257, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=326 `perception_unsettled`: {"ts": 1785219951.89551, "seq": 326, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_strat
- seq=329 `transition_eval`: {"ts": 1785219951.9114869, "seq": 329, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=331 `verification`: {"ts": 1785219951.9117608, "seq": 331, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=338 `forward_predicate_rollback`: {"ts": 1785219952.016683, "seq": 338, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=401 `perception_unsettled`: {"ts": 1785219966.6476412, "seq": 401, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=404 `transition_eval`: {"ts": 1785219966.672162, "seq": 404, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=406 `verification`: {"ts": 1785219966.6726558, "seq": 406, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=413 `forward_predicate_rollback`: {"ts": 1785219966.8509781, "seq": 413, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=476 `perception_unsettled`: {"ts": 1785219980.258479, "seq": 476, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=479 `transition_eval`: {"ts": 1785219980.291144, "seq": 479, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=481 `verification`: {"ts": 1785219980.29174, "seq": 481, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=488 `forward_predicate_rollback`: {"ts": 1785219980.75509, "seq": 488, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward_
- seq=557 `perception_unsettled`: {"ts": 1785219994.350121, "seq": 557, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=560 `transition_eval`: {"ts": 1785219994.369882, "seq": 560, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=562 `verification`: {"ts": 1785219994.3703501, "seq": 562, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=569 `forward_predicate_rollback`: {"ts": 1785219994.506826, "seq": 569, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=632 `perception_unsettled`: {"ts": 1785220007.6505752, "seq": 632, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=635 `transition_eval`: {"ts": 1785220007.67802, "seq": 635, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family": 
- seq=637 `verification`: {"ts": 1785220007.67853, "seq": 637, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=644 `forward_predicate_rollback`: {"ts": 1785220007.897541, "seq": 644, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=707 `perception_unsettled`: {"ts": 1785220020.9379342, "seq": 707, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=710 `transition_eval`: {"ts": 1785220020.953176, "seq": 710, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=712 `verification`: {"ts": 1785220020.9533792, "seq": 712, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=719 `forward_predicate_rollback`: {"ts": 1785220021.060328, "seq": 719, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=788 `perception_unsettled`: {"ts": 1785220034.370829, "seq": 788, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=791 `transition_eval`: {"ts": 1785220034.38708, "seq": 791, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family": 
- seq=793 `verification`: {"ts": 1785220034.387365, "seq": 793, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=800 `forward_predicate_rollback`: {"ts": 1785220034.578924, "seq": 800, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=869 `perception_unsettled`: {"ts": 1785220052.862134, "seq": 869, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=872 `transition_eval`: {"ts": 1785220052.8783581, "seq": 872, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=874 `verification`: {"ts": 1785220052.878528, "seq": 874, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=881 `forward_predicate_rollback`: {"ts": 1785220052.978139, "seq": 881, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=944 `perception_unsettled`: {"ts": 1785220068.75517, "seq": 944, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_strat
- seq=947 `transition_eval`: {"ts": 1785220068.795755, "seq": 947, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=949 `verification`: {"ts": 1785220068.796639, "seq": 949, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=956 `forward_predicate_rollback`: {"ts": 1785220069.1019049, "seq": 956, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1025 `perception_unsettled`: {"ts": 1785220083.5086248, "seq": 1025, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1028 `transition_eval`: {"ts": 1785220083.5242088, "seq": 1028, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1030 `verification`: {"ts": 1785220083.5244548, "seq": 1030, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1037 `forward_predicate_rollback`: {"ts": 1785220084.032437, "seq": 1037, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1100 `perception_unsettled`: {"ts": 1785220097.778187, "seq": 1100, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1103 `transition_eval`: {"ts": 1785220097.8066409, "seq": 1103, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1105 `verification`: {"ts": 1785220097.8071308, "seq": 1105, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1112 `forward_predicate_rollback`: {"ts": 1785220098.074249, "seq": 1112, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1169 `perception_unsettled`: {"ts": 1785220112.060003, "seq": 1169, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1172 `transition_eval`: {"ts": 1785220112.107369, "seq": 1172, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1174 `verification`: {"ts": 1785220112.108313, "seq": 1174, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1181 `forward_predicate_rollback`: {"ts": 1785220112.9603698, "seq": 1181, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=1244 `perception_unsettled`: {"ts": 1785220126.445482, "seq": 1244, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1247 `transition_eval`: {"ts": 1785220126.4931068, "seq": 1247, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1249 `verification`: {"ts": 1785220126.494185, "seq": 1249, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1256 `forward_predicate_rollback`: {"ts": 1785220126.924305, "seq": 1256, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1325 `perception_unsettled`: {"ts": 1785220142.706388, "seq": 1325, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1328 `transition_eval`: {"ts": 1785220142.722749, "seq": 1328, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1330 `verification`: {"ts": 1785220142.723031, "seq": 1330, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1337 `forward_predicate_rollback`: {"ts": 1785220142.839602, "seq": 1337, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1400 `perception_unsettled`: {"ts": 1785220156.604411, "seq": 1400, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1403 `transition_eval`: {"ts": 1785220156.647753, "seq": 1403, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1405 `verification`: {"ts": 1785220156.6484811, "seq": 1405, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1412 `forward_predicate_rollback`: {"ts": 1785220157.174787, "seq": 1412, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1475 `perception_unsettled`: {"ts": 1785220171.567051, "seq": 1475, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1478 `transition_eval`: {"ts": 1785220171.5907369, "seq": 1478, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1480 `verification`: {"ts": 1785220171.591166, "seq": 1480, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1487 `forward_predicate_rollback`: {"ts": 1785220171.7666728, "seq": 1487, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=1550 `perception_unsettled`: {"ts": 1785220188.1769118, "seq": 1550, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1553 `transition_eval`: {"ts": 1785220188.221062, "seq": 1553, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1555 `verification`: {"ts": 1785220188.221987, "seq": 1555, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1562 `forward_predicate_rollback`: {"ts": 1785220189.077536, "seq": 1562, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1631 `perception_unsettled`: {"ts": 1785220202.07246, "seq": 1631, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=1634 `transition_eval`: {"ts": 1785220202.097009, "seq": 1634, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1636 `verification`: {"ts": 1785220202.097568, "seq": 1636, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1643 `forward_predicate_rollback`: {"ts": 1785220202.272193, "seq": 1643, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1706 `perception_unsettled`: {"ts": 1785220215.1159282, "seq": 1706, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1709 `transition_eval`: {"ts": 1785220215.1317399, "seq": 1709, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1711 `verification`: {"ts": 1785220215.131986, "seq": 1711, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1718 `forward_predicate_rollback`: {"ts": 1785220215.2494621, "seq": 1718, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=1787 `perception_unsettled`: {"ts": 1785220228.2617102, "seq": 1787, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1790 `transition_eval`: {"ts": 1785220228.277803, "seq": 1790, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1792 `verification`: {"ts": 1785220228.278104, "seq": 1792, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1799 `forward_predicate_rollback`: {"ts": 1785220228.482827, "seq": 1799, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1868 `perception_unsettled`: {"ts": 1785220242.739147, "seq": 1868, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1871 `transition_eval`: {"ts": 1785220242.754684, "seq": 1871, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1873 `verification`: {"ts": 1785220242.7548969, "seq": 1873, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1880 `forward_predicate_rollback`: {"ts": 1785220242.877345, "seq": 1880, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1949 `perception_unsettled`: {"ts": 1785220255.5878348, "seq": 1949, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1952 `transition_eval`: {"ts": 1785220255.613104, "seq": 1952, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1954 `verification`: {"ts": 1785220255.613638, "seq": 1954, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1961 `forward_predicate_rollback`: {"ts": 1785220255.9577432, "seq": 1961, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2018 `perception_unsettled`: {"ts": 1785220271.214588, "seq": 2018, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2021 `transition_eval`: {"ts": 1785220271.2447062, "seq": 2021, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2023 `verification`: {"ts": 1785220271.245358, "seq": 2023, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2030 `forward_predicate_rollback`: {"ts": 1785220271.455094, "seq": 2030, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2087 `perception_unsettled`: {"ts": 1785220286.784907, "seq": 2087, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2090 `transition_eval`: {"ts": 1785220286.822602, "seq": 2090, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2092 `verification`: {"ts": 1785220286.8232582, "seq": 2092, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=2099 `forward_predicate_rollback`: {"ts": 1785220287.085574, "seq": 2099, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2162 `perception_unsettled`: {"ts": 1785220306.347357, "seq": 2162, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2165 `transition_eval`: {"ts": 1785220306.378994, "seq": 2165, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2167 `verification`: {"ts": 1785220306.379582, "seq": 2167, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2174 `forward_predicate_rollback`: {"ts": 1785220306.6068149, "seq": 2174, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2243 `perception_unsettled`: {"ts": 1785220323.714829, "seq": 2243, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2246 `transition_eval`: {"ts": 1785220323.7310379, "seq": 2246, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2248 `verification`: {"ts": 1785220323.740603, "seq": 2248, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2255 `forward_predicate_rollback`: {"ts": 1785220323.862586, "seq": 2255, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2318 `perception_unsettled`: {"ts": 1785220341.6011012, "seq": 2318, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=2321 `transition_eval`: {"ts": 1785220341.6267169, "seq": 2321, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2323 `verification`: {"ts": 1785220341.627122, "seq": 2323, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2330 `forward_predicate_rollback`: {"ts": 1785220341.810776, "seq": 2330, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2393 `perception_unsettled`: {"ts": 1785220354.889054, "seq": 2393, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2396 `transition_eval`: {"ts": 1785220354.919926, "seq": 2396, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2398 `verification`: {"ts": 1785220354.9206998, "seq": 2398, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=2405 `forward_predicate_rollback`: {"ts": 1785220355.2268312, "seq": 2405, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2468 `perception_unsettled`: {"ts": 1785220374.157111, "seq": 2468, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2471 `transition_eval`: {"ts": 1785220374.1955898, "seq": 2471, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2473 `verification`: {"ts": 1785220374.196197, "seq": 2473, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2480 `forward_predicate_rollback`: {"ts": 1785220374.5697868, "seq": 2480, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2543 `perception_unsettled`: {"ts": 1785220392.1966562, "seq": 2543, "run_id": "wa-forward-live-1785219845", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=2546 `transition_eval`: {"ts": 1785220392.2464042, "seq": 2546, "run_id": "wa-forward-live-1785219845", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2548 `verification`: {"ts": 1785220392.247169, "seq": 2548, "run_id": "wa-forward-live-1785219845", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2555 `forward_predicate_rollback`: {"ts": 1785220392.601844, "seq": 2555, "run_id": "wa-forward-live-1785219845", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2581 `check`: {"ts": 1785220398.361284, "seq": 2581, "run_id": "wa-forward-live-1785219845", "kind": "check", "status": "fail", "name": "forward_task", "expected": "forward 'zarooratwala' from 'Kulvinder' to 'Palla
- seq=2582 `run_end`: {"ts": 1785220398.36145, "seq": 2582, "run_id": "wa-forward-live-1785219845", "kind": "run_end", "status": "fail", "ok": false, "detail": "closed_loop ok=False reason='Maximum step count reached' iter
