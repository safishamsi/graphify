// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./IERC20.sol";
import {Ownable} from "./Ownable.sol";

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    event Transfer(address indexed from, address indexed to, uint256 value);
}

library MathLib {
    function add(uint256 a, uint256 b) internal pure returns (uint256) {
        return a + b;
    }
}

abstract contract Ownable {
    address public owner;
    error NotOwner(address caller);
    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner(msg.sender);
        _;
    }
}

contract Token is IERC20, Ownable {
    using MathLib for uint256;

    enum Status { Active, Paused }
    struct Account { uint256 balance; bool frozen; }

    mapping(address => uint256) public balances;
    Status public status;
    uint256 constant MAX_SUPPLY = 1e27;

    event Minted(address indexed to, uint256 amount);
    error InsufficientBalance(uint256 requested, uint256 available);

    constructor(uint256 initial) {
        owner = msg.sender;
        balances[msg.sender] = initial;
    }

    receive() external payable {}
    fallback() external payable {}

    function transfer(address to, uint256 amount) external override onlyOwner returns (bool) {
        if (balances[msg.sender] < amount) revert InsufficientBalance(amount, balances[msg.sender]);
        balances[msg.sender] = balances[msg.sender].add(amount);
        emit Transfer(msg.sender, to, amount);
        return true;
    }
}

function freeFunction(uint256 x) pure returns (uint256) {
    return x * 2;
}
