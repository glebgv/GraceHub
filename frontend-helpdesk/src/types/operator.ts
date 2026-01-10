export type OperatorRole = 'owner' | 'operator' | 'viewer';

export interface Operator {
  userid: number;
  username?: string;
  firstname?: string;
  role: OperatorRole;
  lastseen?: string;
  activetickets?: number;
  closedtoday?: number;
  avgresponsetime?: number;
}
