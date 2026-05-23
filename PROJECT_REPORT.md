# Design and Implementation of a Monte Carlo Tree Search Based Chinese Checkers Agent

## Acknowledgements

I would like to thank my instructor for providing the Chinese Checkers tournament environment and for defining the rules, time constraints, and scoring system used in this project. I also thank my classmates and test opponents for helping evaluate the agent in different match situations. Their games and observations helped identify practical issues such as repeated moves, timeouts, goal blocking, and the importance of legal move validation.

## Abstract

This project focuses on the design and implementation of an intelligent Chinese Checkers agent for tournament-style play. The original goal was to build a game-playing AI capable of selecting competitive moves under strict timing constraints. Instead of using a neural-network-based reinforcement learning method, the implemented solution uses Monte Carlo Tree Search (MCTS) combined with domain-specific heuristic evaluation. The agent receives the current game state from a socket-based tournament server, rebuilds the board internally, searches through legal moves, evaluates future possibilities through rollouts, and submits a selected move back to the server.

The project includes a complete board representation, legal move generation for single-step and chained jump moves, an MCTS engine, heuristic rollout evaluation, a tournament server, an AI client, a graphical human player, a viewer, and game logging. The agent is optimized using adaptive time limits, move caching, transposition table storage, move pruning, beam-style rollout selection, dynamic heuristic weights, and fallback validation against server-provided legal moves. Experimental logs show 61 recorded games, 45,017 logged moves, an average logged move execution time of 0.181 ms, and a maximum observed result of 10 pins reaching the target goal triangle. The results demonstrate that MCTS with carefully designed heuristics can produce a functional Chinese Checkers agent, while also revealing limitations such as repeated moves, timeout situations, and the lack of learned long-term strategy.

## List of Figures

Figure 1: High-level system architecture of the Chinese Checkers AI system  
Figure 2: MCTS decision-making workflow  
Figure 3: Chinese Checkers board representation using axial coordinates  
Figure 4: Agent decision pipeline from game state to submitted move  
Figure 5: Sample game viewer interface

## List of Tables

Table 1: Project modules and responsibilities  
Table 2: Tournament constraints  
Table 3: MCTS and heuristic parameters  
Table 4: Evaluation metrics from game logs  
Table 5: Strengths, limitations, and future improvements

## 1 Introduction

### 1.1 Project Overview

The project implements an AI player for Chinese Checkers. The agent is designed to connect to a local tournament server, join a game, receive board states, request legal moves, choose a move, and submit that move within the allowed time limit. The game server manages players, turn order, scoring, time limits, legal move validation, and game logs.

The current implementation is best described as a search-based game AI agent. It uses Monte Carlo Tree Search rather than Q-learning, Deep Q-Networks, PPO, SARSA, or another neural reinforcement learning algorithm. The agent still follows the general idea of intelligent decision-making in an environment: it observes the current state, considers possible actions, evaluates future outcomes, and chooses an action. However, the decision process is based on tree search and heuristic evaluation rather than model training.

The main project files are:

| File | Purpose |
| --- | --- |
| `game.py` | Tournament server, game state, scoring, legal move API, timeouts, logging |
| `player.py` | AI client that connects to the server and submits moves |
| `agent.py` | Agent wrapper that rebuilds state and calls MCTS |
| `mcts.py` | Main Monte Carlo Tree Search implementation |
| `mcts_node.py` | MCTS node data structure and UCT calculation |
| `rollout.py` | Rollout policy and heuristic evaluation functions |
| `mcts_utils.py` | Move application, undo, win check, state hashing |
| `checkers_board.py` | Board and cell representation |
| `checkers_pins.py` | Piece representation and legal move generation |
| `human_player.py` | Graphical human player client |
| `viewer.py` | Graphical board viewer |
| `games/` | Saved game logs |

### 1.2 Motivation

Game-playing AI is an important area of artificial intelligence because games provide clear rules, measurable outcomes, and challenging decision spaces. Board games are especially useful because they require planning, adaptation, and efficient search. A good game-playing agent must choose actions that are not only locally valid but also strategically useful several turns later.

Chinese Checkers is challenging because the best move is often not simply the move that advances a piece by one cell. Strong play depends on building and using jump chains, avoiding blocked goal positions, coordinating multiple pieces, and planning over many turns. The action space changes every turn because legal moves depend on the current board occupancy. The agent must also operate under tournament timing constraints, which means it cannot search the entire game tree.

### 1.3 Objectives

The major objectives of the project were:

1. Implement a complete Chinese Checkers game environment with board, pieces, turns, legal moves, and scoring.
2. Build an autonomous AI client that can connect to the server and play without human move selection.
3. Design a decision-making algorithm that selects legal and strategic moves.
4. Optimize the agent so it can make decisions within the tournament time limit.
5. Evaluate gameplay using saved match logs.
6. Identify weaknesses such as repeated moves, blocked goal positions, and timeout behavior.

### 1.4 Scope and Constraints

The scope of the project includes the playable game system, AI client, MCTS decision engine, heuristic evaluation, graphical viewer, and match logging. The project does not currently include neural network training, Q-table learning, policy gradient training, or a learned value function.

The main tournament constraints are:

| Constraint | Value |
| --- | --- |
| Maximum players | 6 |
| Turn timeout | 10 seconds |
| Game time limit | 400 seconds |
| Server port | 50555 |
| Server host | `0.0.0.0` |
| Client default host | `127.0.0.1` |
| Move format | `pin_id` and destination cell index |

The AI must submit only legal moves. To ensure this, the server validates every submitted move. The agent also performs a final validation step before returning a move. If MCTS fails to return a valid move, the agent falls back to the first available legal move.

## 2 Background and Related Work

### 2.1 Overview of Chinese Checkers

Chinese Checkers is a strategy board game played on a star-shaped board. Each player begins with a group of pieces in one triangular home region. The objective is to move all pieces into the opposite target triangle before the opponents do. A move may be a single step to an adjacent empty cell or a jump over an occupied neighboring cell into an empty landing cell. Multiple jumps can be chained in a single turn if each jump is legal.

The implemented board uses a hexagonal coordinate system. Each playable location is represented by axial coordinates `(q, r)`. The board includes a central hexagonal area and six colored triangular regions: red, blue, yellow, purple, lawn green, and gray0. Opposite goal mappings are used to determine each player's target:

| Start color | Target color |
| --- | --- |
| red | blue |
| blue | red |
| yellow | purple |
| purple | yellow |
| lawn green | gray0 |
| gray0 | lawn green |

The win condition is reached when all pieces of a player occupy cells in the opposite target triangle.

### 2.2 Game AI Fundamentals

A game-playing agent observes a state, considers legal actions, evaluates possible outcomes, and chooses an action. In this project:

- The state is the current position of all pieces on the board.
- The actions are legal moves represented as a piece id and a destination cell.
- The environment is the tournament server and board rules.
- The evaluation is a heuristic score estimating how useful a position or move is.
- The objective is to move pieces into the target triangle efficiently while achieving a high tournament score.

The project uses search-based decision-making. Instead of learning a policy through training episodes, it searches possible future moves at decision time and estimates their value using rollouts and heuristics.

### 2.3 Chosen Algorithm: Monte Carlo Tree Search

The chosen algorithm is Monte Carlo Tree Search. MCTS is suitable for games with large branching factors because it does not require exhaustive search. It repeatedly samples promising parts of the game tree and uses the results of simulations to guide future search.

The implemented MCTS follows four main steps:

1. Selection: Starting from the root node, choose child nodes using the UCT score.
2. Expansion: Add a new child node for a promising untried move.
3. Simulation/Rollout: Simulate future play for a limited depth using heuristic move selection.
4. Backpropagation: Update visit counts and values along the path.

The node selection formula is implemented in `mcts_node.py`. Unvisited nodes are explored first. For visited nodes, the score combines average value and an exploration term:

```text
UCT = value / visits + c * sqrt(log(parent_visits) / visits)
```

The project uses an exploration constant of `1.8` during MCTS selection.

MCTS was selected because it handles large action spaces better than full minimax search and can be interrupted after a fixed time limit. This is important because the server imposes a 10-second turn timeout.

### 2.4 Existing Approaches for Board Game AI

Classical game AI often uses minimax search with alpha-beta pruning. This works well for two-player zero-sum games such as chess and checkers, but it is less direct for Chinese Checkers because the branching factor can be high and games can involve more than two players.

MCTS is widely used in board game AI because it can focus search on promising lines instead of exploring every possible move. It is especially useful when a strong heuristic or rollout policy is available.

Reinforcement learning is another common approach. A reinforcement learning agent learns through interaction with an environment by receiving rewards and updating its policy or value function. Examples include Q-learning, Deep Q-Networks, and policy gradient algorithms. These were considered conceptually, but they were not implemented in the current project. Reinforcement learning remains a strong direction for future improvement.

### 2.5 Challenges in Multi-Agent Board Games

Chinese Checkers introduces several practical challenges:

- Large action space due to many pieces and chained jumps.
- Sparse final rewards because winning happens only after many moves.
- Long-term planning because early moves affect later jump opportunities.
- Goal congestion when pieces enter the target triangle in a poor order.
- Repetition and looping when the agent repeatedly moves pieces back and forth.
- Multiple colors and turn orders.
- Strict time limits for tournament play.

These challenges motivated the use of heuristic scoring, move pruning, goal dependency logic, and adaptive time limits.

## 3 System Design

### 3.1 Overall Architecture

The system is divided into five major parts:

1. Game server: Maintains the official game state, player list, turn order, legal move validation, scoring, timeouts, and logs.
2. AI client: Connects to the server, waits for its turn, requests legal moves, calls the agent, and submits the selected move.
3. Board and piece model: Represents cells, coordinates, occupancy, colored regions, and legal movement rules.
4. MCTS engine: Searches possible moves and estimates move quality.
5. Visualization tools: Provide a human player GUI and a board viewer.

The high-level workflow is:

```text
Server creates/hosts game
        |
AI client joins game
        |
Client receives color and player id
        |
On each turn, client requests current state and legal moves
        |
Agent rebuilds internal board state
        |
MCTS searches and evaluates candidate moves
        |
Agent validates selected move
        |
Client submits move to server
        |
Server validates, applies move, logs result, advances turn
```

### 3.2 Environment Design

The board is implemented in `checkers_board.py`. Each cell is represented by a `BoardPosition` object containing:

- Axial coordinate `q`
- Axial coordinate `r`
- Pixel coordinate `x`
- Pixel coordinate `y`
- Position type, such as `board`, `red`, `blue`, or another color
- Occupancy status

The `HexBoard` class builds the full board by generating a central hexagonal region and adding six triangular color zones. It also stores:

- `cells`: list of all board positions
- `index_of`: mapping from axial coordinate to cell index
- `cartesian`: pixel positions for drawing
- `colour_opposites`: mapping from each color to its target triangle

The state representation used by the server is a dictionary mapping each color to a list of occupied cell indices. For example:

```text
"pins": {
  "red": [111, 112, 113, ...],
  "blue": [0, 1, 2, ...]
}
```

The agent reconstructs `Pin` objects from this state before running MCTS.

### 3.3 Legal Move Generation

Legal move generation is implemented in `checkers_pins.py`. Each piece is represented by a `Pin` object containing:

- Board reference
- Current cell index
- Piece id
- Color

The method `getPossibleMoves()` generates all legal destinations for one turn. It supports:

1. Single-step moves to adjacent empty cells.
2. Multi-hop jump moves using stack-based search.
3. Occupancy checks for jumped pieces and landing cells.
4. Returning legal destination cell indices in sorted order.

The six axial movement directions are:

```text
(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)
```

For jumps, the algorithm checks an adjacent cell and a landing cell two steps away. A jump is legal only if the adjacent cell is occupied and the landing cell is empty.

### 3.4 Action Space Design

The tournament server represents actions as:

```text
(pin_id, to_index)
```

Here, `pin_id` identifies which piece is moved, and `to_index` identifies the destination board cell. The server provides legal moves in this format:

```text
{
  "0": [14, 16, 25],
  "1": [17],
  "2": []
}
```

The AI uses this format for final validation and submission. Internally, MCTS expands candidate moves as `(piece_id, destination_index)` pairs.

### 3.5 Heuristic Evaluation Design

The implemented agent uses heuristic evaluation instead of a learned reward model. The heuristic estimates whether a move is useful based on Chinese Checkers strategy.

The main heuristic features are:

- Progress toward the target goal triangle.
- Jump length.
- Directional alignment toward the goal center.
- Future jump potential.
- Piece mobility.
- Center control.
- Goal triangle depth.
- Goal fill ordering.
- Penalty for backward movement.
- Penalty for blocking deeper goal cells.
- Large bonus for winning states.

The move score uses dynamic weights depending on game phase:

| Phase | Condition | Strategy |
| --- | --- | --- |
| Opening | 0 to 2 pieces in goal | Encourage jumps, center control, and mobility |
| Midgame | 3 to 7 pieces in goal | Strongly encourage forward jump chains |
| Endgame | 8 to 10 pieces in goal | Prioritize accurate goal filling and progress |

The goal dependency map encourages deeper goal cells to be filled before shallow entrance cells. This reduces the chance of pieces blocking their own target triangle.

### 3.6 MCTS Decision Mechanism

The MCTS implementation in `mcts.py` uses the current board state and all active colors. It includes:

- Root node creation for the current player.
- UCT-based selection.
- Heuristic move expansion.
- Progressive widening by keeping only top candidate moves.
- Rollout simulation.
- Transposition table lookup.
- Undo logic after simulated moves.
- Visit-count-based final move selection.

The search uses adaptive time limits:

| Condition | MCTS time limit |
| --- | --- |
| More than 40 remaining pieces | 0.20 seconds |
| More than 20 remaining pieces | 0.45 seconds |
| 20 or fewer remaining pieces | 0.90 seconds |

The maximum number of MCTS iterations is 900. These limits keep the agent comfortably below the server's 10-second turn timeout.

### 3.7 Rollout Strategy

Rollouts are implemented in `rollout.py`. A rollout simulates future moves up to a maximum depth of 30. It does not choose moves randomly from all legal actions. Instead, it scores candidate moves, prunes them to the top candidates, and selects one using softmax sampling.

The rollout policy includes:

- Beam pruning to the top 8 moves.
- Softmax move selection with temperature 0.35.
- Dynamic weights for opening, midgame, and endgame.
- Goal dependency logic.
- Locked-piece detection inside the goal triangle.
- Final position evaluation.

The final rollout score rewards the current player for:

- Lower distance to target goal.
- Pieces already inside the target goal.
- Winning the game.

It also subtracts value for opponent progress and applies a goal-blocking penalty.

### 3.8 Opponent Handling Strategy

The server supports up to six players, though most recorded tests appear to be two-player games. Opponents may be human players through `human_player.py`, other clients, or another instance of the AI client. The MCTS engine keeps all colors in the reconstructed board state so that opponent pieces correctly affect move generation and jump opportunities.

The current implementation does not learn a separate model of each opponent. Opponent moves during rollouts are handled by the same heuristic rollout policy.

### 3.9 Handling Invalid or Edge Cases

The project handles several edge cases:

- Illegal moves: The server rejects invalid moves.
- Agent fallback: If MCTS returns no valid move, the agent selects the first available legal move.
- Turn mismatch: The server rejects moves made outside the player's turn.
- Missing player or game: The server returns an error response.
- Draw condition: A draw is detected if all pieces of a player have no legal moves.
- Timeout: The server skips turns that exceed the 10-second turn limit.
- Game time limit: The server ends the game after 400 seconds.
- Locked pieces: The agent avoids moving pieces that are already properly placed in the goal triangle.
- Repeated states: The MCTS engine uses position hashing as a transposition table key.

### 3.10 Performance Optimization

The project includes several performance optimizations:

- Move cache: Avoids repeated legal move computation for the same occupancy pattern.
- Transposition table: Reuses rollout results for previously seen positions.
- Progressive widening: Expands only the most promising moves.
- Beam rollouts: Keeps only the top rollout candidates.
- Adaptive time limit: Uses shorter search time when many pieces remain.
- Rollout depth limit: Stops simulations after 30 plies.
- Apply/undo simulation: Avoids deep-copying the entire board for every simulated move.
- Endgame solver: Uses direct heuristic selection when only a few pieces remain outside the goal.

## 4 Implementation Details

### 4.1 Technology Stack

The project uses:

- Python for all game logic and AI code.
- Socket programming for server-client communication.
- JSON for request and response payloads.
- Tkinter for GUI rendering.
- Plain text log files for game records.

The project does not use PyTorch, TensorFlow, or Gymnasium in the current implementation.

### 4.2 Project Structure

The repository structure is:

```text
chinesecheckers/
  agent.py
  checkers_board.py
  checkers_pins.py
  game.py
  human_player.py
  mcts.py
  mcts_node.py
  mcts_utils.py
  player.py
  rollout.py
  viewer.py
  README.md
  games/
    game_*.log
```

### 4.3 Agent Decision Pipeline

The AI decision process happens mainly in `agent.py` and `player.py`.

The pipeline is:

1. `player.py` connects to the server.
2. The client joins a game and receives a color.
3. On its turn, the client requests legal moves.
4. The client passes the full game state and legal moves to `ChineseCheckersAgent.choose_move()`.
5. The agent clears internal board occupancy.
6. The agent reconstructs all pins from the server state.
7. The agent calls `MCTS.search()`.
8. MCTS returns a candidate `(pin_id, to_index)` move.
9. The agent validates the move against server-provided legal moves.
10. The client submits the move to the server.

The fallback mechanism is important. If MCTS returns `None` or a move not present in the legal move list, the agent safely returns the first available legal move instead of crashing or submitting an illegal move.

### 4.4 Tournament Integration

The server in `game.py` exposes JSON operations through sockets. Important operations include:

| Operation | Purpose |
| --- | --- |
| `join` | Join an available game |
| `start` | Mark player as ready |
| `get_state` | Retrieve public game state |
| `get_legal_moves` | Retrieve legal moves for current player |
| `move` | Submit a selected move |
| `status` | List games and statuses |

The game state includes:

- Game id
- Player list
- Player colors
- Current status
- Pin positions by color
- Move count
- Current turn color
- Turn order
- Last move
- Timeout notice
- Score information

The server validates moves by recomputing legal moves for the selected pin. This protects the game from illegal client behavior.

### 4.5 Scoring System

The server computes a final score using:

```text
final_score = time_score + move_score + pin_goal_score + distance_score
```

The components are:

- `time_score`: rewards lower total time taken.
- `move_score`: rewards a move count near the expected target.
- `pin_goal_score`: gives 100 points for each piece in the target triangle.
- `distance_score`: rewards pieces being closer to target cells.

The score is logged at timeouts, game time limit endings, and game completion.

### 4.6 Logging and Monitoring

Every game creates a log file in the `games/` directory. Logs include:

- Game creation.
- Player joins.
- Game start and turn order.
- Every move.
- Move timing.
- Score lines.
- Turn timeouts.
- Game time limit endings.
- Wins or draws.

These logs are useful for debugging and evaluation. For example, repeated move patterns can be identified by scanning move sequences where the same piece moves between two cells repeatedly.

### 4.7 GUI and Viewer

The project includes `human_player.py` and `viewer.py`. These files provide graphical support for observing or manually playing games. The GUI uses Tkinter and renders the board using the same cell geometry as the core game. The human player can click pieces, view legal moves, and submit moves to the server. The viewer displays the board and game status.

## 5 Experimental Setup

### 5.1 Hardware and Software Configuration

The project was developed and tested on a local Windows system using Python. The server and clients run locally by default using port `50555`. The AI client connects to `127.0.0.1`, while the server listens on `0.0.0.0`, allowing possible LAN play if the client host is changed.

### 5.2 Agent Configuration

The key configuration values are:

| Parameter | Value |
| --- | --- |
| MCTS max iterations | 900 |
| MCTS selection constant | 1.8 |
| Rollout depth | 30 |
| Rollout beam size | 8 |
| Softmax temperature | 0.35 |
| Turn timeout | 10 seconds |
| Game time limit | 400 seconds |
| Opening MCTS time | 0.20 seconds when more than 40 pieces remain |
| Midgame MCTS time | 0.45 seconds when more than 20 pieces remain |
| Late-game MCTS time | 0.90 seconds when 20 or fewer pieces remain |

The heuristic weights change by game phase. Opening gives more importance to center control and developing jump opportunities. Midgame gives high importance to large forward jumps. Endgame gives more importance to direct progress and goal placement.

### 5.3 Evaluation Metrics

The following metrics were used or can be extracted from logs:

- Number of games played.
- Number of moves.
- Average move execution time.
- Median move execution time.
- Average moves per non-empty game.
- Number of wins.
- Number of draws.
- Number of timeout events.
- Final score.
- Pins in goal.
- Distance score.
- Game time limit endings.

### 5.4 Opponent Configurations

The recorded logs include games between named players such as `chetan` and `asha`, using different colors. The system supports human-vs-human, human-vs-agent, and agent-vs-agent configurations depending on which client programs are started. Since the project does not include a separate baseline random agent module, comparisons should be described based on actual tested opponents rather than claimed random-agent experiments.

### 5.5 Tournament Setup

A typical tournament session works as follows:

1. Start the server using `game.py`.
2. Create or wait for a game.
3. Run `player.py` for the AI client.
4. Enter the player name.
5. The client joins the game and receives a color.
6. The game starts when all players are ready.
7. The AI makes moves on its turn.
8. The server logs moves and computes scores.
9. The game ends on win, draw, or time limit.

## 6 Results and Analysis

### 6.1 Log Summary

The `games/` directory contains 61 game log files. From these logs, the following summary was extracted:

| Metric | Value |
| --- | ---: |
| Total log files | 61 |
| Games with `GAME STARTED` entry | 60 |
| Games with zero logged moves | 13 |
| Total logged moves | 45,017 |
| Average move execution time | 0.181 ms |
| Median move execution time | 0.100 ms |
| Average moves per non-zero-move game | 937.9 |
| Turn timeout events | 101 |
| Game time limit events in logs | 130 |
| Wins recorded | 3 |
| Draws recorded | 0 |
| Average final score across final score records | 490.3 |
| Average pins in goal across final score records | 3.48 |
| Maximum final score observed | 1233.3 |
| Maximum pins in goal observed | 10 |

The number of game time limit events is higher than the number of games because the server may log score and game limit messages more than once when the state is requested after the game has already reached the limit.

### 6.2 Gameplay Performance

The agent was able to generate legal moves and participate in full games. Several long games reached hundreds or thousands of moves, showing that the server, move generator, and client loop were stable over long sessions. The maximum observed score was 1233.3, and at least one game achieved all 10 pins in the goal triangle.

The average logged move execution time was very low because the server measures only the time required to apply the already selected move. It does not fully represent the AI search time, which happens on the client before submitting the move. However, the MCTS search itself uses adaptive limits of 0.20, 0.45, or 0.90 seconds, which remain below the 10-second server timeout.

### 6.3 Tournament Results

The logs record three wins:

| Winner | Color |
| --- | --- |
| chetan | lawn green |
| asha | blue |
| asha | blue |

Many games ended due to the 400-second game time limit rather than a direct win. This suggests that the agent and opponents often made progress but did not always finish the game efficiently within the allowed duration.

### 6.4 Top Long Games by Move Count

The longest recorded games by logged moves were:

| Log file | Logged moves | Average move apply time |
| --- | ---: | ---: |
| `game_a6f4a186-c1c7-41ec-954f-54485c3f9f39.log` | 2586 | 0.143 ms |
| `game_172fbb05-78e9-40be-8f2d-9265edab5b33.log` | 2498 | 0.185 ms |
| `game_7e956502-1ac2-476e-a3ce-09f5ae26cc99.log` | 2497 | 0.168 ms |
| `game_6b3e65e7-01d4-4d66-af17-db91ad4f5e1e.log` | 2460 | 0.186 ms |
| `game_71c9c2c9-ef70-451b-b51f-022d20fa635c.log` | 2388 | 0.158 ms |

Long games show that the system can continue running, but they also reveal that the strategy can get stuck in repetitive or inefficient move cycles.

### 6.5 Comparison with Other Agents

The current project does not include a formal random-agent or greedy-agent baseline in the repository. Therefore, a strict statistical comparison against known baseline agents cannot be claimed. Informally, the MCTS agent has advantages over a simple random player because it actively prefers forward progress, large jumps, goal entry, and goal completion. However, without controlled baseline tests, the report should avoid claiming a precise win percentage against random or heuristic opponents.

### 6.6 Unexpected Behaviors Observed

Several important behaviors were observed from gameplay and logs:

1. Repetitive looping: Some games show pieces moving back and forth between the same cells. This indicates that the heuristic sometimes values short-term mobility or local movement over irreversible progress.
2. Long games: Many games reached the game time limit, showing that the agent often made progress but did not always complete all pieces efficiently.
3. Timeout events: Timeout messages appear in the logs, especially when players or clients did not respond in time.
4. Goal congestion: The agent needed goal dependency logic because entering the target triangle too early or in the wrong order can block deeper cells.
5. Aggressive jump preference: The heuristic strongly rewards jumps, which helps movement but can sometimes produce moves that look good immediately but are not best for final completion.

### 6.7 How Issues Were Resolved or Reduced

The implementation includes several mechanisms to reduce the above issues:

- Goal dependency map to encourage deeper goal filling.
- Locked-piece detection to avoid moving correctly placed goal pieces.
- Backward movement penalty.
- Goal-blocking penalty.
- Dynamic weights for opening, midgame, and endgame.
- Beam pruning to reduce weak rollout choices.
- Fallback move validation to prevent illegal submissions.
- Adaptive MCTS time limit to reduce timeout risk.

Some issues remain unresolved. In particular, repeated move loops should be handled with explicit repetition detection and penalties.

## 7 Discussion

### 7.1 Key Findings

The project shows that a Chinese Checkers agent can be built successfully using MCTS and domain-specific heuristics. Legal move generation is central to the project because every AI decision depends on accurate movement rules. MCTS provides a practical balance between decision quality and time constraints. Heuristic design is also extremely important: without good scoring for progress, jumps, goal filling, and blocking, rollouts become noisy and ineffective.

Another key finding is that a fast legal move generator and efficient apply/undo simulation are necessary for search-based agents. The agent cannot afford to copy the full board repeatedly during search. The implemented `apply_move()` and `undo_move()` functions support efficient simulations.

### 7.2 Strengths of the Agent

The main strengths are:

- Generates valid Chinese Checkers moves including chained jumps.
- Uses MCTS instead of a purely greedy one-step decision.
- Uses domain knowledge such as goal depth and directional progress.
- Handles multiple colors and opponent pieces in the state.
- Includes safety fallback for move validity.
- Integrates with a tournament server.
- Logs games for later analysis.
- Provides GUI support for human play and observation.
- Uses adaptive timing to stay below the turn timeout.

### 7.3 Limitations

The main limitations are:

- The current agent is not a trained reinforcement learning model.
- No Q-learning, DQN, PPO, or SARSA implementation is present.
- No neural network policy or value function is used.
- Heuristic weights are manually tuned.
- Repeated move loops can still occur.
- Rollouts are depth-limited and approximate.
- Opponent modeling is simple.
- Formal comparison against baseline agents is not included.
- The logged move time measures server-side move application, not full AI thinking time.
- Some game time limit messages are logged multiple times after the game has already ended.

### 7.4 Lessons Learned

The project demonstrates that building a game-playing agent requires more than choosing an AI algorithm. Board representation, legal move generation, state synchronization, server integration, and logging are equally important. MCTS works well when combined with strong heuristics, but the quality of the heuristic determines whether the search explores useful moves.

The project also shows that Chinese Checkers needs special endgame handling. A piece placed incorrectly in the goal triangle can block other pieces, so the agent must reason about goal fill order. Similarly, repeated moves must be discouraged because they waste turns and prevent completion.

## 8 Future Improvements

### 8.1 Improved Heuristic and Reward Design

Future versions should include explicit repetition penalties, stronger endgame scoring, and better detection of moves that permanently improve the position. The scoring function could also be tuned using automated experiments instead of manual weight selection.

### 8.2 Better Opponent Modeling

The current rollout policy treats opponents using the same general heuristic. A stronger agent could model opponent goals more accurately, block opponent jump chains, and avoid creating useful jump paths for opponents.

### 8.3 Multi-Agent Self-Play Enhancements

Self-play could be used to generate many games automatically. The results could help tune heuristic weights or train a learned evaluation function. Multiple versions of the agent could play against each other to compare strategies.

### 8.4 Search and Reinforcement Learning Hybrid Approaches

A future version could combine MCTS with reinforcement learning. Possible approaches include:

- MCTS plus a learned value function.
- MCTS plus a learned policy prior.
- Reinforcement learning for heuristic weight tuning.
- Deep Q-learning over encoded board states.
- PPO or policy gradient training through self-play.

This would move the project closer to the original reinforcement learning goal while preserving the strengths of search-based planning.

### 8.5 Larger Training and Evaluation Infrastructure

The project would benefit from scripts that automatically run batches of matches, parse logs, compute metrics, and generate graphs. Parallel simulations could also increase the number of games tested.

## 9 Conclusion

This project successfully implements a Chinese Checkers AI system with a tournament server, AI client, board model, legal move generator, MCTS decision engine, rollout evaluator, GUI tools, and logging. The agent uses Monte Carlo Tree Search with domain-specific heuristics rather than neural reinforcement learning. It can connect to the server, observe the board, choose legal moves, and compete in timed games.

The experimental logs show that the system is functional over many games and thousands of moves. The agent can achieve strong progress, including games with all 10 pins reaching the goal. However, the results also reveal important limitations such as repeated move loops, long games ending by time limit, and the absence of learned strategy. Overall, the project provides a strong foundation for a Chinese Checkers AI agent and can be extended in the future with reinforcement learning, better opponent modeling, automatic evaluation, and improved endgame planning.

## References

1. Coulom, R. (2006). Efficient selectivity and backup operators in Monte-Carlo tree search.
2. Kocsis, L., and Szepesvari, C. (2006). Bandit based Monte-Carlo planning.
3. Browne, C. B., Powley, E., Whitehouse, D., Lucas, S. M., Cowling, P. I., Rohlfshagen, P., Tavener, S., Perez, D., Samothrakis, S., and Colton, S. (2012). A survey of Monte Carlo Tree Search methods.
4. Sutton, R. S., and Barto, A. G. Reinforcement Learning: An Introduction.
5. Russell, S., and Norvig, P. Artificial Intelligence: A Modern Approach.
6. Project source files: `game.py`, `player.py`, `agent.py`, `mcts.py`, `rollout.py`, `checkers_board.py`, and `checkers_pins.py`.

## Appendices

### Appendix A: MCTS Parameters and Heuristic Weights

| Parameter | Value |
| --- | --- |
| UCT exploration constant | 1.8 |
| Maximum MCTS iterations | 900 |
| Rollout depth | 30 |
| Rollout candidate beam size | 8 |
| Softmax temperature | 0.35 |
| Win bonus in rollout | 50,000 |
| Goal occupancy reward in rollout | 250 per piece |
| Goal blocking penalty | 250 per blocking case |
| Goal fill dependency violation penalty | 200 |

Dynamic scoring weights:

| Phase | Jump weight | Progress weight | Center weight | Future jump weight |
| --- | ---: | ---: | ---: | ---: |
| Opening | 120 | 35 | 25 | 20 |
| Midgame | 170 | 55 | 10 | 30 |
| Endgame | 80 | 80 | 0 | 10 |

### Appendix B: Sample Game State Format

```json
{
  "game_id": "example-game-id",
  "status": "PLAYING",
  "pins": {
    "red": [111, 112, 113, 114, 115],
    "blue": [0, 1, 2, 3, 4]
  },
  "move_count": 12,
  "current_turn_colour": "red",
  "turn_order": ["red", "blue"],
  "last_move": {
    "by": "player1",
    "colour": "blue",
    "from": 3,
    "to": 14,
    "move_ms": 0.1
  }
}
```

### Appendix C: Sample Legal Move Format

```json
{
  "0": [14, 16],
  "1": [17, 29, 31],
  "2": []
}
```

The key is the piece id and the value is the list of legal destination cell indices.

### Appendix D: Additional Match Statistics

From the available log files:

| Statistic | Value |
| --- | ---: |
| Log files | 61 |
| Started games | 60 |
| Total logged moves | 45,017 |
| Average move application time | 0.181 ms |
| Median move application time | 0.100 ms |
| Turn timeout events | 101 |
| Wins | 3 |
| Draws | 0 |
| Maximum pins in goal | 10 |

### Appendix E: Source Code Repository Link

Repository/path:

```text
C:\Users\hp\PycharmProjects\chinesecheckers
```

If submitting the project online, replace this local path with the final GitHub or institutional repository link.
