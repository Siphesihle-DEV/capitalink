// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";

/// @notice Audit trail for SME financing events. Stores amounts in cents and hashes only: no personal or confidential data.
contract SMEFinancingRegistry is AccessControl {
    bytes32 public constant RELAYER_ROLE = keccak256("RELAYER_ROLE");

    enum Kind { Registered, Allocated, Disbursed, Repaid, Distributed }
    struct Entry { Kind kind; uint256 amountCents; uint256 principalCents; uint256 interestCents; bytes32 ref; uint64 timestamp; }
    struct Financing { uint256 principalCents; bytes32 dataHash; bool exists; }

    mapping(bytes32 => Financing) private financings;
    mapping(bytes32 => Entry[]) private history;
    mapping(bytes32 => bool) public usedRef; // blocks duplicate submissions

    event FinancingApproved(bytes32 indexed id, uint256 principalCents, bytes32 dataHash);
    event CapitalAllocated(bytes32 indexed id, uint256 amountCents, bytes32 ref);
    event DisbursementRecorded(bytes32 indexed id, uint256 amountCents, bytes32 ref);
    event RepaymentRecorded(bytes32 indexed id, uint256 amountCents, uint256 principalCents, uint256 interestCents, bytes32 ref);
    event InvestorDistributionRecorded(bytes32 indexed id, uint256 amountCents, bytes32 ref);

    constructor(address relayer) {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(RELAYER_ROLE, relayer);
    }

    modifier known(bytes32 id) { require(financings[id].exists, "unknown financing"); _; }
    modifier fresh(bytes32 ref) { require(!usedRef[ref], "duplicate ref"); usedRef[ref] = true; _; }

    function registerFinancing(bytes32 id, uint256 principalCents, bytes32 dataHash) external onlyRole(RELAYER_ROLE) {
        require(!financings[id].exists, "already registered");
        financings[id] = Financing(principalCents, dataHash, true);
        history[id].push(Entry(Kind.Registered, principalCents, 0, 0, dataHash, uint64(block.timestamp)));
        emit FinancingApproved(id, principalCents, dataHash);
    }

    function recordAllocation(bytes32 id, uint256 amountCents, bytes32 ref) external onlyRole(RELAYER_ROLE) known(id) fresh(ref) {
        history[id].push(Entry(Kind.Allocated, amountCents, 0, 0, ref, uint64(block.timestamp)));
        emit CapitalAllocated(id, amountCents, ref);
    }

    function recordDisbursement(bytes32 id, uint256 amountCents, bytes32 ref) external onlyRole(RELAYER_ROLE) known(id) fresh(ref) {
        history[id].push(Entry(Kind.Disbursed, amountCents, 0, 0, ref, uint64(block.timestamp)));
        emit DisbursementRecorded(id, amountCents, ref);
    }

    function recordRepayment(bytes32 id, uint256 amountCents, uint256 principalCents, uint256 interestCents, bytes32 ref)
        external onlyRole(RELAYER_ROLE) known(id) fresh(ref) {
        require(principalCents + interestCents == amountCents, "split mismatch");
        history[id].push(Entry(Kind.Repaid, amountCents, principalCents, interestCents, ref, uint64(block.timestamp)));
        emit RepaymentRecorded(id, amountCents, principalCents, interestCents, ref);
    }

    function recordDistribution(bytes32 id, uint256 amountCents, bytes32 ref) external onlyRole(RELAYER_ROLE) known(id) fresh(ref) {
        history[id].push(Entry(Kind.Distributed, amountCents, 0, 0, ref, uint64(block.timestamp)));
        emit InvestorDistributionRecorded(id, amountCents, ref);
    }

    function getFinancing(bytes32 id) external view returns (Financing memory) { return financings[id]; }
    function getFinancingHistory(bytes32 id) external view returns (Entry[] memory) { return history[id]; }
}
